"""Tiny TCP bridge for AgentDojo 0.1.35's localhost-only local LLM adapter."""

import asyncio
import os

LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = int(os.getenv("LOCAL_LLM_PORT", "8000"))
TARGET_HOST = os.getenv("OLLAMA_TARGET_HOST", "host.docker.internal")
TARGET_PORT = int(os.getenv("OLLAMA_TARGET_PORT", "11434"))


async def relay(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


async def handle(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter) -> None:
    try:
        target_reader, target_writer = await asyncio.open_connection(TARGET_HOST, TARGET_PORT)
        await asyncio.gather(
            relay(client_reader, target_writer),
            relay(target_reader, client_writer),
        )
    except Exception as exc:
        print(f"bridge connection failed: {exc}", flush=True)
        client_writer.close()
        await client_writer.wait_closed()


async def main() -> None:
    server = await asyncio.start_server(handle, LISTEN_HOST, LISTEN_PORT)
    print(
        f"AgentDojo local-LLM bridge: {LISTEN_HOST}:{LISTEN_PORT} -> {TARGET_HOST}:{TARGET_PORT}",
        flush=True,
    )
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
