import { mkdir, readdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { startHttpMcpServer } from "../shared/http-server.js";
import { dataDir, safeChildPath } from "../shared/paths.js";

const reportsDir = path.join(dataDir, "reports");

function reportFilename(filename: string): string {
  const base = path.basename(filename);
  return base.endsWith(".md") ? base : `${base}.md`;
}

function createServer(): McpServer {
  const server = new McpServer(
    { name: "business-report-mcp", version: "1.0.0" },
    { instructions: "Save completed business briefs as Markdown with save_report." }
  );

  server.registerTool(
    "save_report",
    {
      description: "Save a completed Markdown business brief.",
      inputSchema: {
        filename: z.string().min(1),
        content: z.string().min(1)
      },
      annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: true }
    },
    async ({ filename, content }) => {
      await mkdir(reportsDir, { recursive: true });
      const normalized = reportFilename(filename);
      await writeFile(safeChildPath(reportsDir, normalized), content, "utf8");
      const output = { saved: true, filename: normalized, characters: content.length };
      return {
        content: [{ type: "text", text: `Saved ${normalized}` }],
        structuredContent: output
      };
    }
  );

  server.registerTool(
    "list_reports",
    {
      description: "List saved Markdown business briefs.",
      inputSchema: {},
      annotations: { readOnlyHint: true }
    },
    async () => {
      await mkdir(reportsDir, { recursive: true });
      const reports = (await readdir(reportsDir)).filter(file => file.endsWith(".md"));
      const output = { reports };
      return {
        content: [{ type: "text", text: JSON.stringify(output, null, 2) }],
        structuredContent: output
      };
    }
  );

  server.registerTool(
    "read_report",
    {
      description: "Read a saved Markdown business brief.",
      inputSchema: { filename: z.string().min(1) },
      annotations: { readOnlyHint: true }
    },
    async ({ filename }) => {
      const normalized = reportFilename(filename);
      const content = await readFile(safeChildPath(reportsDir, normalized), "utf8");
      const output = { filename: normalized, content };
      return {
        content: [{ type: "text", text: content }],
        structuredContent: output
      };
    }
  );

  return server;
}

startHttpMcpServer({
  name: "business-report-mcp",
  port: Number(process.env.PORT ?? 9103),
  createServer
});
