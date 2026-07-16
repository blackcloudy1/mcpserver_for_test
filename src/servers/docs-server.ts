import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { startHttpMcpServer } from "../shared/http-server.js";
import { dataDir, safeChildPath } from "../shared/paths.js";

const docsDir = path.join(dataDir, "docs");

function createServer(): McpServer {
  const server = new McpServer(
    { name: "business-docs-mcp", version: "1.0.0" },
    { instructions: "Use search_docs to find product documents, then read_doc to read the selected document." }
  );

  server.registerTool(
    "search_docs",
    {
      description: "Search local Markdown product documents by filename and content.",
      inputSchema: { keyword: z.string().min(1) },
      annotations: { readOnlyHint: true }
    },
    async ({ keyword }) => {
      const files = (await readdir(docsDir)).filter(file => file.endsWith(".md"));
      const lowered = keyword.toLocaleLowerCase();
      const matches: Array<{ filename: string; preview: string }> = [];

      for (const filename of files) {
        const content = await readFile(safeChildPath(docsDir, filename), "utf8");
        if (filename.toLocaleLowerCase().includes(lowered) || content.toLocaleLowerCase().includes(lowered)) {
          matches.push({ filename, preview: content.replace(/\s+/g, " ").slice(0, 160) });
        }
      }

      const output = { keyword, matches };
      return {
        content: [{ type: "text", text: JSON.stringify(output, null, 2) }],
        structuredContent: output
      };
    }
  );

  server.registerTool(
    "read_doc",
    {
      description: "Read one Markdown document returned by search_docs.",
      inputSchema: { filename: z.string().min(1) },
      annotations: { readOnlyHint: true }
    },
    async ({ filename }) => {
      const content = await readFile(safeChildPath(docsDir, filename), "utf8");
      const output = { filename: path.basename(filename), content };
      return {
        content: [{ type: "text", text: content }],
        structuredContent: output
      };
    }
  );

  return server;
}

startHttpMcpServer({
  name: "business-docs-mcp",
  port: Number(process.env.PORT ?? 9101),
  createServer
});
