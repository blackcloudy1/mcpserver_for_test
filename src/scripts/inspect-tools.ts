import { listTools } from "../shared/mcp-client.js";

const host = process.env.MCP_SERVER_HOST ?? "127.0.0.1";
const servers = {
  business_docs: `http://${host}:9101/mcp`,
  business_sales: `http://${host}:9102/mcp`,
  business_report: `http://${host}:9103/mcp`
};

const inventory: Record<string, unknown> = {};
for (const [serverId, url] of Object.entries(servers)) {
  inventory[serverId] = await listTools(url);
}

console.log(JSON.stringify(inventory, null, 2));
