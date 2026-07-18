import os
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .normalization import decode_base64_once, normalize_text

app = FastAPI(title="Agent Security Lab", version="0.1.0")
OPA_URL = os.getenv("OPA_URL", "http://opa:8181/v1/data/agent_security/decision")
SIDE_EFFECT_TOOLS = {"file.write", "shell.exec", "http.request", "git.push", "agent.spawn"}


class NormalizeRequest(BaseModel):
    text: str = Field(max_length=100_000)


class PolicyRequest(BaseModel):
    tool: dict[str, Any]
    context: dict[str, Any] = Field(default_factory=dict)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/normalize")
async def normalize(request: NormalizeRequest) -> dict[str, object]:
    result = normalize_text(request.text)
    result["base64_decoded_once"] = decode_base64_once(str(result["normalized"]))
    return result


@app.post("/policy/evaluate")
async def evaluate(request: PolicyRequest) -> dict[str, object]:
    tool_name = str(request.tool.get("name", ""))
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.post(OPA_URL, json={"input": request.model_dump()})
            response.raise_for_status()
            result = response.json().get("result")
            if not isinstance(result, dict):
                raise ValueError("OPA returned no decision")
            return result
    except (httpx.HTTPError, ValueError) as exc:
        if tool_name in SIDE_EFFECT_TOOLS:
            return {"decision": "deny", "risk": "high", "reasons": ["policy_engine_unavailable"]}
        raise HTTPException(status_code=503, detail="policy engine unavailable") from exc
