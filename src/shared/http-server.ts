import type { Request, Response } from "express";
import { createMcpExpressApp } from "@modelcontextprotocol/sdk/server/express.js";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";

type ServerFactory = () => McpServer;

export function startHttpMcpServer(options: {
  name: string;
  port: number;
  createServer: ServerFactory;
}): void {
  const host = process.env.MCP_HOST ?? "0.0.0.0";
  const apiToken = process.env.MCP_API_TOKEN;
  const maxPending = Number(process.env.MCP_MAX_PENDING_REQUESTS ?? 16);
  const maxRequestBytes = Number(process.env.MCP_MAX_REQUEST_BYTES ?? 1024 * 1024);
  const allowedOrigins = new Set(
    (process.env.MCP_ALLOWED_ORIGINS ?? "")
      .split(",")
      .map(origin => origin.trim())
      .filter(Boolean)
  );
  const allowedHosts = (process.env.MCP_ALLOWED_HOSTS ?? "")
    .split(",")
    .map(value => value.trim())
    .filter(Boolean);
  let pendingRequests = 0;

  // Keep the SDK's DNS-rebinding policy consistent with the address passed to
  // app.listen(). Previously createMcpExpressApp() defaulted to 127.0.0.1 and
  // rejected valid Docker service names even though the server bound 0.0.0.0.
  const app = createMcpExpressApp({
    host,
    ...(allowedHosts.length > 0 ? { allowedHosts } : {})
  });

  app.get("/health", (_req, res) => {
    res.json({ status: "ok", server: options.name });
  });

  app.post("/mcp", async (req: Request, res: Response) => {
    const origin = req.header("origin");
    if (origin && allowedOrigins.size > 0 && !allowedOrigins.has(origin)) {
      res.status(403).json({ error: "origin_not_allowed" });
      return;
    }

    const contentLength = Number(req.header("content-length") ?? 0);
    if (contentLength > maxRequestBytes) {
      res.status(413).json({ error: "request_too_large" });
      return;
    }

    if (apiToken) {
      const authorization = req.header("authorization");
      if (authorization !== `Bearer ${apiToken}`) {
        res.status(401).json({ error: "unauthorized" });
        return;
      }
    }

    if (pendingRequests >= maxPending) {
      res.status(503).json({ error: "too_many_pending_requests" });
      return;
    }
    pendingRequests += 1;

    const server = options.createServer();
    const transport = new StreamableHTTPServerTransport({
      sessionIdGenerator: undefined,
      enableJsonResponse: true
    });

    res.once("close", () => {
      void transport.close();
      void server.close();
    });

    try {
      await server.connect(transport);
      await transport.handleRequest(req, res, req.body);
    } catch (error) {
      console.error(`[${options.name}] request failed`, error);
      if (!res.headersSent) {
        res.status(500).json({
          jsonrpc: "2.0",
          error: { code: -32603, message: "Internal server error" },
          id: null
        });
      }
    } finally {
      pendingRequests -= 1;
    }
  });

  app.get("/mcp", (_req, res) => {
    res.status(405).json({ error: "This stateless server accepts MCP POST requests only." });
  });

  app.delete("/mcp", (_req, res) => {
    res.status(405).json({ error: "This stateless server does not keep sessions." });
  });

  app.listen(options.port, host, error => {
    if (error) {
      console.error(`[${options.name}] failed to start`, error);
      process.exit(1);
    }
    console.log(`[${options.name}] http://${host}:${options.port}/mcp`);
  });
}

