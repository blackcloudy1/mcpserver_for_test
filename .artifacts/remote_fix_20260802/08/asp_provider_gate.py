"""Promptfoo-provider adapter around the Agent Security Platform input gate."""

import os

from asp_input_gate import InputGateError, evaluate_prompt


def guard_provider(prompt, identity):
    if os.environ.get("ASP_RULE_GATE_ENABLED", "1").lower() in {
        "0", "false", "no", "off",
    }:
        return None, {"mode": "disabled-for-ablation", "decision": "allow"}
    try:
        gate = evaluate_prompt(
            prompt, identity.get("session_id") or identity.get("canary") or "", identity
        )
    except InputGateError as exc:
        detail = str(exc)[-4000:]
        evidence = _evidence(identity, {"mode": "rule-only-enforced", "decision": "error"})
        evidence.update({
            "classification": "platform_input_gate_error",
            "infrastructureError": True,
            "infrastructureErrors": [detail],
        })
        return {
            "error": f"Agent Security Platform input gate failed: {detail}",
            "metadata": {"clineEvidence": evidence},
        }, evidence["platform"]
    if gate["decision"] not in {"confirm", "block"}:
        return None, gate
    evidence = _evidence(identity, gate)
    evidence.update({
        "classification": "blocked_by_agent_security_platform",
        "infrastructureError": False,
        "infrastructureErrors": [],
        "signals": {},
        "toolCounts": {"started": 0, "completed": 0, "failed": 0, "blocked": 1},
        "fileChanges": {
            "added": [], "modified": [], "deleted": [], "truncated": False,
        },
    })
    return {
        "output": (
            "Agent Security Platform blocked this input before it reached Cline "
            f"(decision={gate['decision']})."
        ),
        "metadata": {"clineEvidence": evidence},
    }, gate


def _evidence(identity, platform):
    return {
        "version": 1,
        "canary": identity.get("canary", ""),
        "evaluationId": identity.get("evaluation_id", ""),
        "testStepId": identity.get("test_step_id", ""),
        "pluginId": identity.get("plugin_id", ""),
        "strategyId": identity.get("strategy_id", ""),
        "sessionId": identity.get("session_id", ""),
        "platform": platform,
    }
