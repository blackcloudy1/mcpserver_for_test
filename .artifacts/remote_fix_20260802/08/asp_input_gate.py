#!/usr/bin/env python3
"""Rule-only Agent Security Platform input gate used by the Promptfoo provider."""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request


BACKEND_URL = os.environ.get("ASP_BACKEND_URL", "http://127.0.0.1:18080").rstrip("/")
TOKEN_FILE = os.environ.get(
    "ASP_TOKEN_FILE", "/home/fcx/.config/agent-security/cline.jwt"
)
TIMEOUT_SECONDS = float(os.environ.get("ASP_INPUT_GATE_TIMEOUT_SECONDS", "20"))
MAX_CONTENT_CHARS = 262_144


class InputGateError(RuntimeError):
    pass


def _post(path: str, payload: dict, token: str) -> dict:
    request = urllib.request.Request(
        f"{BACKEND_URL}{path}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            value = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read(2048).decode("utf-8", errors="replace")
        raise InputGateError(f"HTTP {exc.code} from {path}: {detail}") from exc
    except (OSError, ValueError) as exc:
        raise InputGateError(f"Agent Security Platform request failed: {exc}") from exc
    if not isinstance(value, dict):
        raise InputGateError(f"Invalid JSON object returned by {path}")
    return value


def evaluate_prompt(prompt: str, session_id: str, identity: dict) -> dict:
    if len(prompt) > MAX_CONTENT_CHARS:
        raise InputGateError(
            f"Prompt exceeds platform input limit ({len(prompt)} > {MAX_CONTENT_CHARS})"
        )
    try:
        with open(TOKEN_FILE, encoding="utf-8") as handle:
            token = handle.read().strip()
    except OSError as exc:
        raise InputGateError(f"Cannot read platform token file: {exc}") from exc
    if not token:
        raise InputGateError("Agent Security Platform token file is empty")

    effective_session = (session_id or identity.get("canary") or "")[:64]
    trace = _post(
        "/api/traces",
        {
            "session_id": effective_session,
            "original_user_intent": prompt,
        },
        token,
    )
    trace_id = str(trace.get("trace_id") or "")
    if not trace_id:
        raise InputGateError("Trace creation returned no trace_id")

    source_id = "promptfoo-" + hashlib.sha256(
        f"{trace_id}|{prompt}".encode("utf-8")
    ).hexdigest()[:32]
    result = _post(
        "/api/gateway/external-content",
        {
            "trace_id": trace_id,
            "session_id": effective_session,
            "source": {
                "source_type": "rag_document",
                "source_id": source_id,
                "origin": "promptfoo-cline-input-gate",
                "document": prompt,
                "title": "Promptfoo rendered Cline input",
                "collection": "promptfoo-evaluation",
                "metadata": {
                    "plugin_id": str(identity.get("plugin_id") or "")[:128],
                    "strategy_id": str(identity.get("strategy_id") or "")[:128],
                    "language": str(identity.get("language") or "")[:64],
                },
            },
        },
        token,
    )
    decision = result.get("decision")
    if decision not in {"allow", "confirm", "block"}:
        raise InputGateError(f"Invalid platform decision: {decision!r}")
    finding = result.get("finding")
    return {
        "mode": "rule-only-enforced",
        "decision": decision,
        "decisionReason": str(result.get("decision_reason") or ""),
        "traceId": trace_id,
        "eventId": str(result.get("event_id") or ""),
        "sourceId": source_id,
        "detected": bool(finding.get("detected")) if isinstance(finding, dict) else False,
        "detectorVersion": (
            str(finding.get("detector_version") or "")
            if isinstance(finding, dict)
            else ""
        ),
    }
