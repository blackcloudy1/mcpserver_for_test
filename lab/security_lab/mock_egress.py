from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI

app = FastAPI(title="Local Mock Egress Sink")
events: list[dict[str, Any]] = []


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/collect")
async def collect(payload: dict[str, Any]) -> dict[str, object]:
    event = {"received_at": datetime.now(timezone.utc).isoformat(), "payload": payload}
    events.append(event)
    return {"accepted": True, "event_count": len(events)}


@app.get("/events")
async def list_events() -> dict[str, object]:
    return {"events": events}


@app.delete("/events")
async def clear_events() -> dict[str, bool]:
    events.clear()
    return {"cleared": True}
