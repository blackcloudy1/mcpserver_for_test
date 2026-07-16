import { mkdir, readdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { startHttpMcpServer } from "../shared/http-server.js";
import { dataDir, safeChildPath } from "../shared/paths.js";

const reportsDir = path.join(dataDir, "reports");
const maxReportBytes = Number(process.env.MCP_MAX_TOOL_RESULT_BYTES ?? 256 * 1024);

function reportFilename(filename: string): string {
  // Validate the caller-supplied value before adding the extension. Do not
  // silently normalize paths such as "../sales.csv" into a safe-looking name.
  safeChildPath(reportsDir, filename);
  return filename.endsWith(".md") ? filename : `${filename}.md`;
}

function createServer(): McpServer {
  const server = new McpServer(
    { name: "business-report-mcp", version: "1.0.0" },
    { instructions: "Save completed business briefs as Markdown with save_report." }
  );

  server.registerTool(
    "save_report",
    {
      description: "Write a Markdown business brief into the fixed reports directory. Requires report:write and should require human confirmation.",
      inputSchema: {
        filename: z.string().min(1),
        content: z.string().min(1),
        overwrite: z.boolean().default(false)
      },
      annotations: { readOnlyHint: false, destructiveHint: true, idempotentHint: true }
    },
    async ({ filename, content, overwrite }) => {
      await mkdir(reportsDir, { recursive: true });
      if (Buffer.byteLength(content, "utf8") > maxReportBytes) {
        return {
          content: [{ type: "text", text: `Report exceeds the ${maxReportBytes}-byte limit` }],
          isError: true
        };
      }
      const normalized = reportFilename(filename);
      try {
        await writeFile(safeChildPath(reportsDir, normalized), content, {
          encoding: "utf8",
          flag: overwrite ? "w" : "wx"
        });
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code === "EEXIST") {
          return {
            content: [{ type: "text", text: `${normalized} already exists; set overwrite=true to replace it` }],
            isError: true
          };
        }
        throw error;
      }
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
