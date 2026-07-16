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
  const app = createMcpExpressApp();

  app.get("/health", (_req, res) => {
    res.json({ status: "ok", server: options.name });
  });

  app.post("/mcp", async (req: Request, res: Response) => {
    if (apiToken) {
      const authorization = req.header("authorization");
      if (authorization !== `Bearer ${apiToken}`) {
        res.status(401).json({ error: "unauthorized" });
        return;
      }
    }

    const server = options.createServer();
    const transport = new StreamableHTTPServerTransport({
      sessionIdGenerator: undefined,
      enableJsonResponse: true
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
      res.on("close", () => {
        void transport.close();
        void server.close();
      });
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
