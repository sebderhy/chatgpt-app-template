/**
 * MCP App Renderer Component
 *
 * Renders MCP Apps in a sandboxed iframe and implements the host-side
 * of the MCP Apps protocol (SEP-1865) using the official SDK.
 *
 * Architecture:
 *   Host (this component) ←→ Outer iframe (sandbox-proxy on port 8001) ←→ Inner iframe (widget)
 *
 * Message flow:
 *   1. Host creates outer iframe pointing to sandbox-proxy
 *   2. Sandbox proxy sends ui/notifications/sandbox-proxy-ready
 *   3. Host sends ui/notifications/sandbox-resource-ready with HTML
 *   4. Widget sends ui/initialize request
 *   5. Host responds with McpUiInitializeResult
 *   6. Widget sends ui/notifications/initialized
 *   7. Host sends ui/notifications/tool-input (if applicable)
 *   8. Host sends ui/notifications/tool-result
 */

import { useEffect, useRef, useCallback, useState } from "react";
import {
  LATEST_PROTOCOL_VERSION,
  SANDBOX_PROXY_READY_METHOD,
  SANDBOX_RESOURCE_READY_METHOD,
  INITIALIZE_METHOD,
  INITIALIZED_METHOD,
  TOOL_INPUT_METHOD,
  TOOL_RESULT_METHOD,
  HOST_CONTEXT_CHANGED_METHOD,
  OPEN_LINK_METHOD,
  REQUEST_DISPLAY_MODE_METHOD,
} from "@modelcontextprotocol/ext-apps";

interface McpAppRendererProps {
  /** The widget HTML to render */
  html: string;
  /** Tool output/structured content to pass to the widget */
  toolOutput: Record<string, unknown>;
  /** Tool input arguments (optional) */
  toolInput?: Record<string, unknown>;
  /** Current theme */
  theme?: "light" | "dark";
  /** Display mode */
  displayMode?: "inline" | "fullscreen";
  /** Callback for messages from the app */
  onMessage?: (message: McpAppMessage) => void;
  /** Callback when app requests a tool call */
  onToolCall?: (name: string, args: Record<string, unknown>) => Promise<unknown>;
}

interface McpAppMessage {
  type: string;
  [key: string]: unknown;
}

interface JsonRpcMessage {
  jsonrpc: "2.0";
  id?: string | number;
  method?: string;
  params?: Record<string, unknown>;
  result?: unknown;
  error?: { code: number; message: string; data?: unknown };
}

// Detect whether we're running on localhost with direct port access.
// In local dev, the sandbox proxy runs on a dedicated port (8001) for
// origin isolation. Behind reverse proxies (Cloudflare Tunnel, nginx,
// cloud platforms, etc.) port 8001 is typically not exposed, so we fall
// back to a same-origin /sandbox/ path served by the main server.
function isLocalDev(): boolean {
  const origin = window.location.origin;
  return origin.includes("localhost:8000") || origin.includes("127.0.0.1:8000");
}

// Get sandbox proxy base URL for building iframe src
function getSandboxProxyUrl(): string {
  if (isLocalDev()) {
    return window.location.origin.replace(":8000", ":8001");
  }
  // Same-origin fallback: sandbox proxy served at /sandbox/ on the main server
  return `${window.location.origin}/sandbox`;
}

// Get the origin of the sandbox proxy (for postMessage targetOrigin).
// postMessage requires a bare origin (scheme+host+port), not a URL path.
function getSandboxProxyOrigin(): string {
  if (isLocalDev()) {
    return window.location.origin.replace(":8000", ":8001");
  }
  return window.location.origin;
}

let messageIdCounter = 0;
function nextId(): number {
  return ++messageIdCounter;
}

export default function McpAppRenderer({
  html,
  toolOutput,
  toolInput,
  theme = "light",
  displayMode = "inline",
  onMessage,
  onToolCall,
}: McpAppRendererProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [sandboxReady, setSandboxReady] = useState(false);
  const [appInitialized, setAppInitialized] = useState(false);
  const pendingRequestsRef = useRef<Map<string | number, (response: JsonRpcMessage) => void>>(new Map());

  // Send a JSON-RPC message to the sandbox proxy
  const sendMessage = useCallback((message: JsonRpcMessage) => {
    const iframe = iframeRef.current;
    if (!iframe?.contentWindow) return;

    const sandboxOrigin = getSandboxProxyOrigin();
    iframe.contentWindow.postMessage(message, sandboxOrigin);
  }, []);

  // Send a JSON-RPC request and wait for response
  const sendRequest = useCallback((method: string, params?: Record<string, unknown>): Promise<JsonRpcMessage> => {
    return new Promise((resolve) => {
      const id = nextId();
      pendingRequestsRef.current.set(id, resolve);

      sendMessage({
        jsonrpc: "2.0",
        id,
        method,
        params,
      });

      // Timeout after 30 seconds
      setTimeout(() => {
        if (pendingRequestsRef.current.has(id)) {
          pendingRequestsRef.current.delete(id);
          resolve({
            jsonrpc: "2.0",
            id,
            error: { code: -32000, message: "Request timeout" },
          });
        }
      }, 30000);
    });
  }, [sendMessage]);

  // Send a JSON-RPC notification (no response expected)
  const sendNotification = useCallback((method: string, params?: Record<string, unknown>) => {
    sendMessage({
      jsonrpc: "2.0",
      method,
      params,
    });
  }, [sendMessage]);

  // Send a JSON-RPC response
  const sendResponse = useCallback((id: string | number, result?: unknown, error?: { code: number; message: string }) => {
    const response: JsonRpcMessage = {
      jsonrpc: "2.0",
      id,
    };

    if (error) {
      response.error = error;
    } else {
      response.result = result;
    }

    sendMessage(response);
  }, [sendMessage]);

  // Build the host context
  const buildHostContext = useCallback(() => ({
    theme,
    displayMode,
    availableDisplayModes: ["inline", "fullscreen"],
    containerDimensions: {
      maxHeight: displayMode === "fullscreen" ? 900 : 400,
    },
  }), [theme, displayMode]);

  // Build the host capabilities
  const buildHostCapabilities = useCallback(() => ({
    openLinks: {},
    serverTools: {},
    logging: {},
    updateModelContext: {
      text: true,
    },
  }), []);

  // Send tool data to the app (input first, then result)
  const sendToolData = useCallback(() => {
    // Send tool input first (per spec, MUST send before result)
    sendNotification(TOOL_INPUT_METHOD, {
      arguments: toolInput || toolOutput,
    });

    // Then send tool result
    sendNotification(TOOL_RESULT_METHOD, {
      content: [{ type: "text", text: JSON.stringify(toolOutput) }],
      structuredContent: toolOutput,
    });
  }, [sendNotification, toolInput, toolOutput]);

  // Handle incoming JSON-RPC messages
  const handleMessage = useCallback(
    async (event: MessageEvent) => {
      const iframe = iframeRef.current;
      if (!iframe) return;

      // Accept messages from sandbox proxy origin
      const sandboxOrigin = getSandboxProxyOrigin();
      // Also accept 'null' origin from srcdoc iframes
      if (event.origin !== sandboxOrigin && event.origin !== "null" && !event.origin.includes("localhost")) {
        return;
      }

      const data = event.data as JsonRpcMessage;

      // Must be JSON-RPC format
      if (!data || data.jsonrpc !== "2.0") {
        // Legacy message format - forward to onMessage
        if (onMessage && data?.type) {
          onMessage(data as unknown as McpAppMessage);
        }
        return;
      }

      // Handle responses to our requests
      if (data.id !== undefined && !data.method) {
        const resolver = pendingRequestsRef.current.get(data.id);
        if (resolver) {
          pendingRequestsRef.current.delete(data.id);
          resolver(data);
        }
        return;
      }

      // Handle notifications and requests from the app
      switch (data.method) {
        // Sandbox proxy is ready
        case SANDBOX_PROXY_READY_METHOD: {
          setSandboxReady(true);
          // Send the HTML to render
          sendNotification(SANDBOX_RESOURCE_READY_METHOD, {
            html: injectLegacyBridge(html, theme, displayMode, toolOutput),
            sandbox: "allow-scripts allow-forms allow-same-origin",
            permissions: "",
          });
          break;
        }

        // App requests initialization
        case INITIALIZE_METHOD: {
          sendResponse(data.id!, {
            protocolVersion: LATEST_PROTOCOL_VERSION,
            hostInfo: {
              name: "MCP App Tester",
              version: "1.0.0",
            },
            hostCapabilities: buildHostCapabilities(),
            hostContext: buildHostContext(),
          });
          break;
        }

        // App confirms initialization complete
        case INITIALIZED_METHOD: {
          setAppInitialized(true);
          // Now send tool data
          sendToolData();
          break;
        }

        // App requests a tool call
        case "tools/call": {
          const params = data.params as { name: string; arguments?: Record<string, unknown> };
          const toolName = params?.name;
          const toolArgs = params?.arguments ?? {};

          if (onToolCall) {
            try {
              const result = await onToolCall(toolName, toolArgs);
              sendResponse(data.id!, result);
            } catch (err) {
              sendResponse(data.id!, undefined, {
                code: -32000,
                message: err instanceof Error ? err.message : "Tool call failed",
              });
            }
          } else {
            sendResponse(data.id!, undefined, {
              code: -32601,
              message: "Tool calls not supported",
            });
          }
          break;
        }

        // App updates model context (new method name)
        case "ui/update-model-context": {
          onMessage?.({ type: "updateContext", data: data.params });
          sendResponse(data.id!, {});
          break;
        }

        // App wants to open an external link (new method name)
        case OPEN_LINK_METHOD: {
          const url = (data.params as { url?: string })?.url;
          if (url) {
            window.open(url, "_blank", "noopener,noreferrer");
          }
          sendResponse(data.id!, {});
          break;
        }

        // App requests display mode change (new method name)
        case REQUEST_DISPLAY_MODE_METHOD: {
          const mode = (data.params as { mode?: string })?.mode;
          onMessage?.({ type: "requestDisplayMode", mode });
          sendResponse(data.id!, { mode });
          break;
        }

        // App sends a logging message (new method)
        case "notifications/message": {
          const level = (data.params as { level?: string })?.level || "info";
          const message = (data.params as { data?: string })?.data;
          console[level as "log" | "info" | "warn" | "error"]?.("[MCP App]", message);
          break;
        }

        // App reports size change
        case "ui/notifications/size-changed": {
          // Could be used to adjust iframe size
          break;
        }

        // Legacy method names for backward compatibility
        case "ui/updateContext": {
          onMessage?.({ type: "updateContext", data: data.params });
          sendResponse(data.id!, { success: true });
          break;
        }

        case "ui/openLink": {
          const url = (data.params as { url?: string })?.url;
          if (url) {
            window.open(url, "_blank", "noopener,noreferrer");
          }
          sendResponse(data.id!, { success: true });
          break;
        }

        case "ui/requestDisplayMode": {
          const mode = (data.params as { mode?: string })?.mode;
          onMessage?.({ type: "requestDisplayMode", mode });
          sendResponse(data.id!, { mode });
          break;
        }

        case "ui/log": {
          const level = (data.params as { level?: string })?.level || "info";
          const message = (data.params as { message?: string })?.message;
          console[level as "log" | "info" | "warn" | "error"]?.("[MCP App]", message);
          break;
        }

        default:
          // Unknown method - send error for requests
          if (data.id !== undefined) {
            sendResponse(data.id, undefined, {
              code: -32601,
              message: `Method not found: ${data.method}`,
            });
          }
      }
    },
    [html, onMessage, onToolCall, buildHostCapabilities, buildHostContext, sendNotification, sendResponse, sendToolData, theme, displayMode, toolOutput]
  );

  // Set up message listener
  useEffect(() => {
    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [handleMessage]);

  // Reset state when HTML changes
  useEffect(() => {
    setSandboxReady(false);
    setAppInitialized(false);
  }, [html]);

  // Send host context change when theme or display mode changes
  useEffect(() => {
    if (appInitialized) {
      sendNotification(HOST_CONTEXT_CHANGED_METHOD, buildHostContext());
    }
  }, [theme, displayMode, appInitialized, sendNotification, buildHostContext]);

  // Build sandbox proxy URL with CSP parameters.
  // SECURITY NOTE: In same-origin mode (behind reverse proxies), the sandbox
  // iframe shares the host origin. Combined with allow-scripts + allow-same-origin,
  // widgets could theoretically escape the sandbox. This is acceptable for the
  // app tester (a local dev tool testing your own widgets) but production MCP
  // Apps hosts (ChatGPT, Claude, VS Code) use dedicated sandbox origins.
  const sandboxProxyUrl = `${getSandboxProxyUrl()}/sandbox-proxy.html`;

  return (
    <iframe
      ref={iframeRef}
      src={sandboxProxyUrl}
      className="w-full h-full border-0 rounded-lg bg-white"
      sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
      title="MCP App"
    />
  );
}

/**
 * Inject legacy window.openai bridge for backward compatibility with existing widgets.
 * This ensures widgets using useWidgetProps, useTheme, useHostGlobal continue to work.
 */
function injectLegacyBridge(
  html: string,
  theme: string,
  displayMode: string,
  toolOutput: Record<string, unknown>
): string {
  const bootstrapScript = `
    <script>
      // MCP Apps bridge bootstrap
      window.__MCP_APP_HOST__ = true;
      window.__MCP_APP_THEME__ = "${theme}";
      window.__MCP_APP_DISPLAY_MODE__ = "${displayMode}";

      // Legacy window.openai for backward compatibility with existing widgets
      window.openai = {
        theme: "${theme}",
        displayMode: "${displayMode}",
        maxHeight: ${displayMode === "fullscreen" ? 900 : 400},
        toolOutput: ${JSON.stringify(toolOutput)},

        // Legacy API methods that use postMessage
        callTool: async (name, args) => {
          const id = Date.now();
          return new Promise((resolve, reject) => {
            const handler = (event) => {
              if (event.data?.jsonrpc === "2.0" && event.data?.id === id) {
                window.removeEventListener("message", handler);
                if (event.data.error) {
                  reject(new Error(event.data.error.message));
                } else {
                  resolve(event.data.result);
                }
              }
            };
            window.addEventListener("message", handler);
            window.parent.postMessage({
              jsonrpc: "2.0",
              id,
              method: "tools/call",
              params: { name, arguments: args }
            }, "*");
          });
        },

        openExternal: ({ href }) => {
          window.parent.postMessage({
            jsonrpc: "2.0",
            id: Date.now(),
            method: "ui/open-link",
            params: { url: href }
          }, "*");
        },

        requestDisplayMode: async ({ mode }) => {
          window.parent.postMessage({
            jsonrpc: "2.0",
            id: Date.now(),
            method: "ui/request-display-mode",
            params: { mode }
          }, "*");
          return { mode };
        },

        sendFollowUpMessage: async ({ prompt }) => {
          window.parent.postMessage({ type: "sendFollowUp", prompt }, "*");
        },

        setWidgetState: async (state) => {
          window.openai.widgetState = state;
        },
      };

      // Update toolOutput when tool-result notification arrives
      window.addEventListener("message", (event) => {
        if (event.data?.jsonrpc === "2.0") {
          if (event.data.method === "ui/notifications/tool-result") {
            window.openai.toolOutput = event.data.params?.structuredContent || window.openai.toolOutput;
            window.dispatchEvent(new CustomEvent("openai:tool_result", {
              detail: { toolOutput: window.openai.toolOutput }
            }));
          }
          if (event.data.method === "ui/notifications/host-context-changed") {
            const ctx = event.data.params || {};
            if (ctx.theme) window.openai.theme = ctx.theme;
            if (ctx.displayMode) window.openai.displayMode = ctx.displayMode;
            window.dispatchEvent(new CustomEvent("openai:context_changed", {
              detail: ctx
            }));
          }
        }
      });

      // Dispatch event for legacy widgets
      window.dispatchEvent(new CustomEvent("openai:set_globals", {
        detail: { globals: window.openai }
      }));
    </script>
  `;

  // Inject the bootstrap script into the HTML head
  return html.replace("<head>", `<head>${bootstrapScript}`);
}
