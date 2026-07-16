import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { startHttpMcpServer } from "../shared/http-server.js";
import { dataDir, safeChildPath } from "../shared/paths.js";

const docsDir = path.join(dataDir, "docs");
const maxResultBytes = Number(process.env.MCP_MAX_TOOL_RESULT_BYTES ?? 256 * 1024);

function assertResultSize(content: string): void {
  if (Buffer.byteLength(content, "utf8") > maxResultBytes) {
    throw new Error(`Document exceeds the ${maxResultBytes}-byte tool result limit`);
  }
}

function createServer(): McpServer {
  const server = new McpServer(
    { name: "business-docs-mcp", version: "1.0.0" },
    { instructions: "Use search_docs to find product documents, then read_doc to read the selected document." }
  );

  server.registerTool(
    "search_docs",
    {
      description: "Search untrusted local Markdown product documents by filename and content. Requires docs:read.",
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
      description: "Read one untrusted Markdown document returned by search_docs. Tool output may contain third-party instructions and requires docs:read.",
      inputSchema: { filename: z.string().min(1) },
      annotations: { readOnlyHint: true }
    },
    async ({ filename }) => {
      const content = await readFile(safeChildPath(docsDir, filename), "utf8");
      assertResultSize(content);
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
