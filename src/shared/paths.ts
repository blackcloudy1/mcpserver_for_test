import path from "node:path";

export const dataDir = path.resolve(process.env.MCP_DATA_DIR ?? path.join(process.cwd(), "data"));

export function safeChildPath(parent: string, filename: string): string {
  const nativeName = path.basename(filename);
  const windowsName = path.win32.basename(filename);
  const posixName = path.posix.basename(filename);

  if (!filename || filename !== nativeName || filename !== windowsName || filename !== posixName) {
    throw new Error("Only a plain filename is allowed; directory components are forbidden");
  }

  const resolved = path.resolve(parent, filename);
  const relative = path.relative(parent, resolved);

  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error("Invalid filename");
  }
  return resolved;
}
