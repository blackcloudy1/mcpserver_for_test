import path from "node:path";

export const dataDir = path.resolve(process.env.MCP_DATA_DIR ?? path.join(process.cwd(), "data"));

export function safeChildPath(parent: string, filename: string): string {
  const safeName = path.basename(filename);
  const resolved = path.resolve(parent, safeName);
  const relative = path.relative(parent, resolved);

  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error("Invalid filename");
  }
  return resolved;
}
