import { callTool } from "../shared/mcp-client.js";

const baseHost = process.env.MCP_SERVER_HOST ?? "127.0.0.1";
const product = process.env.DEMO_PRODUCT ?? "产品A";
const month = process.env.DEMO_MONTH ?? "2026-07";

const docsUrl = `http://${baseHost}:9101/mcp`;
const salesUrl = `http://${baseHost}:9102/mcp`;
const reportUrl = `http://${baseHost}:9103/mcp`;

const search = await callTool(docsUrl, "search_docs", { keyword: product });
const matches = search.matches as Array<{ filename: string }>;
if (!matches?.length) throw new Error(`No document found for ${product}`);

const doc = await callTool(docsUrl, "read_doc", { filename: matches[0].filename });
const summary = await callTool(salesUrl, "get_sales_summary", { product, month });
const ranking = await callTool(salesUrl, "get_top_regions", { product, month, limit: 3 });
const regions = ranking.regions as Array<{ region: string; units: number; revenue: number }>;

const markdown = `# ${product} ${month} 经营简报

## 产品资料

${String(doc.content)}

## 销售概况

- 销量：${summary.units}
- 销售额：¥${summary.revenue}
- 覆盖区域：${summary.region_count}

## 区域排名

${regions.map((row, index) => `${index + 1}. ${row.region}：${row.units} 件，¥${row.revenue}`).join("\n")}
`;

const saved = await callTool(reportUrl, "save_report", {
  filename: `${product}-${month}.md`,
  content: markdown,
  overwrite: true
});

console.log(JSON.stringify({ product, month, saved }, null, 2));
