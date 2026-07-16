import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";

export type ToolOutput = Record<string, unknown>;

function transportFor(url: string): StreamableHTTPClientTransport {
  const token = process.env.MCP_API_TOKEN;
  return new StreamableHTTPClientTransport(new URL(url), {
    requestInit: token ? { headers: { Authorization: `Bearer ${token}` } } : undefined
  });
}

export async function callTool(
  url: string,
  name: string,
  args: Record<string, unknown>
): Promise<ToolOutput> {
  const client = new Client({ name: "business-brief-test-client", version: "1.0.0" });
  await client.connect(transportFor(url));
  try {
    const result = await client.callTool({ name, arguments: args });
    if (result.isError) throw new Error(JSON.stringify(result.content));
    return (result.structuredContent ?? {}) as ToolOutput;
  } finally {
    await client.close();
  }
}

export async function listTools(url: string): Promise<unknown> {
  const client = new Client({ name: "business-tool-inspector", version: "1.0.0" });
  await client.connect(transportFor(url));
  try {
    return await client.listTools();
  } finally {
    await client.close();
  }
}
