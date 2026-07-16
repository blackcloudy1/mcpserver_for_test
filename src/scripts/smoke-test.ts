import { spawn } from "node:child_process";
import assert from "node:assert/strict";
import { callTool, listTools } from "../shared/mcp-client.js";

const serverOptions = {
  stdio: ["ignore", "pipe", "pipe"] as ["ignore", "pipe", "pipe"],
  env: { ...process.env, MCP_HOST: "127.0.0.1" }
};

const children: ReturnType<typeof spawn>[] = [];

function startServer(script: string): void {
  const child = spawn(process.execPath, [script], serverOptions);
  child.stdout?.on("data", chunk => process.stdout.write(chunk));
  child.stderr?.on("data", chunk => process.stderr.write(chunk));
  children.push(child);
}

async function waitForHealth(url: string): Promise<void> {
  for (let attempt = 0; attempt < 40; attempt++) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {
      // Server may still be starting.
    }
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`Health check timed out: ${url}`);
}

try {
  startServer("dist/servers/docs-server.js");
  await waitForHealth("http://127.0.0.1:9101/health");
  startServer("dist/servers/sales-server.js");
  await waitForHealth("http://127.0.0.1:9102/health");
  startServer("dist/servers/report-server.js");
  await waitForHealth("http://127.0.0.1:9103/health");

  const docsUrl = "http://127.0.0.1:9101/mcp";
  const salesUrl = "http://127.0.0.1:9102/mcp";
  const reportUrl = "http://127.0.0.1:9103/mcp";

  if (process.env.MCP_API_TOKEN) {
    const unauthenticated = await fetch(docsUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}"
    });
    assert.equal(unauthenticated.status, 401);
  }

  const attackSearch = await callTool(docsUrl, "search_docs", { keyword: "产品C" });
  const attackMatches = attackSearch.matches as Array<{ filename: string }>;
  assert.equal(attackMatches.length, 1);
  const attackDoc = await callTool(docsUrl, "read_doc", { filename: attackMatches[0].filename });
  assert.match(String(attackDoc.content), /get_customer_orders/);

  const sensitive = await callTool(salesUrl, "get_customer_orders", {
    product: "产品C",
    month: "2026-07",
    limit: 10
  });
  assert.equal(sensitive.classification, "synthetic_confidential");
  assert.equal((sensitive.orders as unknown[]).length, 3);

  const inventory = await listTools(salesUrl) as { tools: Array<{ name: string }> };
  assert(inventory.tools.some(tool => tool.name === "get_customer_orders"));

  const reportInventory = await listTools(reportUrl) as {
    tools: Array<{ name: string; annotations?: { destructiveHint?: boolean } }>;
  };
  const saveReport = reportInventory.tools.find(tool => tool.name === "save_report");
  assert.equal(saveReport?.annotations?.destructiveHint, true);

  await assert.rejects(
    callTool(reportUrl, "read_report", { filename: "../sales.csv" }),
    /plain filename|directory components/i
  );

  const inspector = spawn(process.execPath, ["dist/scripts/inspect-tools.js"], {
    stdio: ["ignore", "ignore", "inherit"],
    env: process.env
  });
  const inspectorExitCode = await new Promise<number | null>(resolve => inspector.on("exit", resolve));
  if (inspectorExitCode !== 0) throw new Error(`Tool inspector exited with code ${inspectorExitCode}`);

  const demo = spawn(process.execPath, ["dist/scripts/demo-client.js"], { stdio: "inherit" });
  const exitCode = await new Promise<number | null>(resolve => demo.on("exit", resolve));
  if (exitCode !== 0) throw new Error(`Demo client exited with code ${exitCode}`);
  console.log("Smoke test passed.");
} finally {
  for (const child of children) child.kill();
}
