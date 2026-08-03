import { spawn, type ChildProcess } from "node:child_process";
import { networkInterfaces } from "node:os";

const servers = [
  { name: "business_docs", entry: "dist/servers/docs-server.js", port: "19101" },
  { name: "business_sales", entry: "dist/servers/sales-server.js", port: "19102" },
  { name: "business_report", entry: "dist/servers/report-server.js", port: "19103" }
];

const children: ChildProcess[] = [];
const host = "0.0.0.0";
const detectedHosts = new Set(["localhost", "127.0.0.1", "[::1]"]);

for (const addresses of Object.values(networkInterfaces())) {
  for (const address of addresses ?? []) {
    if (address.family === "IPv4") detectedHosts.add(address.address);
  }
}

const allowedHosts = process.env.MCP_ALLOWED_HOSTS ?? [...detectedHosts].join(",");

for (const server of servers) {
  const child = spawn(process.execPath, [server.entry], {
    stdio: "inherit",
    env: {
      ...process.env,
      // start:all is the LAN launcher. Do not inherit a stale loopback-only
      // MCP_HOST value from the parent shell.
      MCP_HOST: host,
      // Enable the SDK's Host-header validation while still accepting the
      // machine's current LAN/VMware interface addresses.
      MCP_ALLOWED_HOSTS: allowedHosts,
      PORT: server.port
    }
  });

  children.push(child);
  child.once("exit", (code, signal) => {
    console.error(`${server.name} stopped (code=${code ?? "none"}, signal=${signal ?? "none"})`);
    shutdown(code ?? 1);
  });
}

let shuttingDown = false;

function shutdown(exitCode = 0): void {
  if (shuttingDown) return;
  shuttingDown = true;
  for (const child of children) {
    if (!child.killed) child.kill();
  }
  process.exitCode = exitCode;
}

process.once("SIGINT", () => shutdown());
process.once("SIGTERM", () => shutdown());
