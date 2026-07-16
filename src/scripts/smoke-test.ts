import { spawn } from "node:child_process";

const serverOptions = {
  stdio: ["ignore", "pipe", "pipe"] as ["ignore", "pipe", "pipe"],
  env: { ...process.env, MCP_HOST: "127.0.0.1" }
};

const children = [
  spawn(process.execPath, ["dist/servers/docs-server.js"], serverOptions),
  spawn(process.execPath, ["dist/servers/sales-server.js"], serverOptions),
  spawn(process.execPath, ["dist/servers/report-server.js"], serverOptions)
];

for (const child of children) {
  child.stdout?.on("data", chunk => process.stdout.write(chunk));
  child.stderr?.on("data", chunk => process.stderr.write(chunk));
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
  await Promise.all([
    waitForHealth("http://127.0.0.1:9101/health"),
    waitForHealth("http://127.0.0.1:9102/health"),
    waitForHealth("http://127.0.0.1:9103/health")
  ]);

  const demo = spawn(process.execPath, ["dist/scripts/demo-client.js"], { stdio: "inherit" });
  const exitCode = await new Promise<number | null>(resolve => demo.on("exit", resolve));
  if (exitCode !== 0) throw new Error(`Demo client exited with code ${exitCode}`);
  console.log("Smoke test passed.");
} finally {
  for (const child of children) child.kill();
}
