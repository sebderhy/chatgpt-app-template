/**
 * MCP Apps Sandbox Proxy
 *
 * This is a minimal relay that runs in the outer iframe on a different origin
 * from the host. It receives HTML content from the host and renders it in an
 * inner iframe, relaying all postMessage traffic bidirectionally.
 *
 * Architecture:
 *   Host (port 8000) ←→ Outer iframe (port 8001) ←→ Inner iframe (srcdoc)
 *
 * This provides origin isolation so the widget cannot access the host's cookies,
 * localStorage, or other same-origin resources.
 */

// Protocol method constants (inline to avoid importing full SDK)
const SANDBOX_PROXY_READY_METHOD = "ui/notifications/sandbox-proxy-ready";
const SANDBOX_RESOURCE_READY_METHOD = "ui/notifications/sandbox-resource-ready";
const LATEST_PROTOCOL_VERSION = "2026-01-26";

// Types for the sandbox resource message
interface SandboxResourceParams {
  html: string;
  sandbox?: string;
  csp?: {
    resourceDomains?: string[];
    connectDomains?: string[];
  };
  permissions?: string;
}

interface JsonRpcMessage {
  jsonrpc: "2.0";
  method?: string;
  params?: Record<string, unknown>;
  id?: string | number;
  result?: unknown;
  error?: unknown;
}

// Get the host origin from the parent window.
// In local dev, the sandbox runs on port 8001 and the host on port 8000.
// Behind reverse proxies, both share the same origin (served at /sandbox/).
function getHostOrigin(): string {
  // Referrer is the most reliable signal — the parent page that loaded us
  if (document.referrer) {
    const url = new URL(document.referrer);
    return url.origin;
  }
  // Same-origin mode: sandbox proxy served at /sandbox/ on the main server
  if (window.location.pathname.startsWith("/sandbox/")) {
    return window.location.origin;
  }
  // Fallback: localhost dev — sandbox on 8001, host on 8000
  return window.location.origin.replace(":8001", ":8000");
}

// Track the inner iframe
let innerIframe: HTMLIFrameElement | null = null;
const hostOrigin = getHostOrigin();

// Validate that a message came from a trusted origin
function isValidOrigin(origin: string): boolean {
  // Accept messages from the host origin
  if (origin === hostOrigin) return true;
  // Accept messages from ourselves (inner iframe via srcdoc has null origin)
  if (origin === "null") return true;
  // Accept localhost variants for development
  if (origin.includes("localhost") || origin.includes("127.0.0.1")) return true;
  return false;
}

// Send a message to the host
function sendToHost(message: JsonRpcMessage): void {
  window.parent.postMessage(message, hostOrigin);
}

// Send a notification to the host
function sendNotification(method: string, params?: Record<string, unknown>): void {
  sendToHost({
    jsonrpc: "2.0",
    method,
    params,
  });
}

// Create the inner iframe with the widget HTML
function createInnerIframe(params: SandboxResourceParams): void {
  // Remove existing iframe if present
  if (innerIframe) {
    innerIframe.remove();
  }

  // Create new iframe
  innerIframe = document.createElement("iframe");

  // Apply sandbox attributes
  const sandbox = params.sandbox || "allow-scripts allow-forms";
  innerIframe.sandbox.value = sandbox;

  // Apply permissions policy if provided
  if (params.permissions) {
    innerIframe.allow = params.permissions;
  }

  // Style the iframe to fill the container
  innerIframe.style.cssText = "width:100%;height:100%;border:none;background:transparent;";

  // Add to DOM first (needed for document.write approach)
  document.body.appendChild(innerIframe);

  // Inject the HTML using document.write for better compatibility
  // This works better than srcdoc for script execution timing
  const doc = innerIframe.contentDocument;
  if (doc) {
    doc.open();
    doc.write(params.html);
    doc.close();
  } else {
    // Fallback to srcdoc if contentDocument not available
    innerIframe.srcdoc = params.html;
  }
}

// Handle messages from host or inner iframe
function handleMessage(event: MessageEvent): void {
  // Validate origin
  if (!isValidOrigin(event.origin)) {
    return;
  }

  const data = event.data as JsonRpcMessage;

  // Must be JSON-RPC format
  if (!data || data.jsonrpc !== "2.0") {
    return;
  }

  // Message from host (parent window)
  if (event.source === window.parent) {
    // Check for sandbox resource ready notification
    if (data.method === SANDBOX_RESOURCE_READY_METHOD) {
      const params = data.params as unknown as SandboxResourceParams;
      if (params?.html) {
        createInnerIframe(params);
      }
      return;
    }

    // Relay all other host messages to inner iframe
    if (innerIframe?.contentWindow) {
      innerIframe.contentWindow.postMessage(data, "*");
    }
    return;
  }

  // Message from inner iframe
  if (event.source === innerIframe?.contentWindow) {
    // Relay to host
    sendToHost(data);
    return;
  }
}

// Initialize the sandbox proxy
function init(): void {
  // Set up full-viewport styles for the proxy container
  const style = document.createElement("style");
  style.textContent = `
    html, body {
      margin: 0;
      padding: 0;
      width: 100%;
      height: 100%;
      overflow: hidden;
      background: transparent;
    }
  `;
  document.head.appendChild(style);

  // Set up message listener
  window.addEventListener("message", handleMessage);

  // Notify host that we're ready
  sendNotification(SANDBOX_PROXY_READY_METHOD, {
    protocolVersion: LATEST_PROTOCOL_VERSION,
  });
}

// Start when DOM is ready
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
