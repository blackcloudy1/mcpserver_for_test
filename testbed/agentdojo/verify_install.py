import importlib.metadata
import json

from agentdojo.attacks.attack_registry import ATTACKS
from agentdojo.models import ModelsEnum

print(
    json.dumps(
        {
            "agentdojo_version": importlib.metadata.version("agentdojo"),
            "attacks": sorted(ATTACKS),
            "models": sorted(str(model) for model in ModelsEnum),
            "roles": {
                "victim_agent": "AgentDojo AgentPipeline + configured LLM backend",
                "adversary": "AgentDojo attack implementation",
                "evaluator": "AgentDojo utility/security scorers",
            },
        },
        indent=2,
    )
)
