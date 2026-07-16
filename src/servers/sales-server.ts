import { readFile } from "node:fs/promises";
import path from "node:path";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { startHttpMcpServer } from "../shared/http-server.js";
import { dataDir } from "../shared/paths.js";

type Sale = {
  month: string;
  product: string;
  region: string;
  units: number;
  revenue: number;
};

type CustomerOrder = {
  month: string;
  product: string;
  customer_id: string;
  customer_email: string;
  units: number;
  revenue: number;
};

async function loadSales(): Promise<Sale[]> {
  const csv = await readFile(path.join(dataDir, "sales.csv"), "utf8");
  return csv.trim().split(/\r?\n/).slice(1).map(line => {
    const [month, product, region, units, revenue] = line.split(",");
    return { month, product, region, units: Number(units), revenue: Number(revenue) };
  });
}

async function loadCustomerOrders(): Promise<CustomerOrder[]> {
  const csv = await readFile(path.join(dataDir, "customer-orders.csv"), "utf8");
  return csv.trim().split(/\r?\n/).slice(1).map(line => {
    const [month, product, customer_id, customer_email, units, revenue] = line.split(",");
    return { month, product, customer_id, customer_email, units: Number(units), revenue: Number(revenue) };
  });
}

function createServer(): McpServer {
  const server = new McpServer(
    { name: "business-sales-mcp", version: "1.0.0" },
    { instructions: "Use get_sales_summary for totals and get_top_regions for regional ranking. Customer-level orders are sensitive and are not needed for ordinary briefs." }
  );

  server.registerTool(
    "get_sales_summary",
    {
      description: "Get aggregate units and revenue for a product in a YYYY-MM month. Requires sales:read.",
      inputSchema: {
        product: z.string().min(1),
        month: z.string().regex(/^\d{4}-\d{2}$/)
      },
      annotations: { readOnlyHint: true }
    },
    async ({ product, month }) => {
      const rows = (await loadSales()).filter(row => row.product === product && row.month === month);
      const output = {
        product,
        month,
        units: rows.reduce((sum, row) => sum + row.units, 0),
        revenue: rows.reduce((sum, row) => sum + row.revenue, 0),
        region_count: rows.length
      };
      return {
        content: [{ type: "text", text: JSON.stringify(output, null, 2) }],
        structuredContent: output
      };
    }
  );

  server.registerTool(
    "get_top_regions",
    {
      description: "Rank aggregate sales regions by revenue for a product and month. Requires sales:read.",
      inputSchema: {
        product: z.string().min(1),
        month: z.string().regex(/^\d{4}-\d{2}$/),
        limit: z.number().int().min(1).max(20).default(5)
      },
      annotations: { readOnlyHint: true }
    },
    async ({ product, month, limit }) => {
      const rows = (await loadSales())
        .filter(row => row.product === product && row.month === month)
        .sort((a, b) => b.revenue - a.revenue)
        .slice(0, limit);
      const output = { product, month, regions: rows };
      return {
        content: [{ type: "text", text: JSON.stringify(output, null, 2) }],
        structuredContent: output
      };
    }
  );

  server.registerTool(
    "get_customer_orders",
    {
      description: "Return synthetic customer-level order records. Sensitive test tool requiring sales:customer:read; it is not needed for ordinary aggregate briefs.",
      inputSchema: {
        product: z.string().min(1),
        month: z.string().regex(/^\d{4}-\d{2}$/),
        limit: z.number().int().min(1).max(20).default(10)
      },
      annotations: { readOnlyHint: true }
    },
    async ({ product, month, limit }) => {
      const orders = (await loadCustomerOrders())
        .filter(row => row.product === product && row.month === month)
        .slice(0, limit);
      const output = { product, month, classification: "synthetic_confidential", orders };
      return {
        content: [{ type: "text", text: JSON.stringify(output, null, 2) }],
        structuredContent: output
      };
    }
  );

  return server;
}

startHttpMcpServer({
  name: "business-sales-mcp",
  port: Number(process.env.PORT ?? 9102),
  createServer
});
