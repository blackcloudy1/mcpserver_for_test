package agent_security_test

import rego.v1
import data.agent_security.decision

test_safe_read_is_allowed if {
  result := decision with input as {"tool": {"name": "docs.search", "arguments": {"query": "安全"}}, "context": {"mode": "read_only", "contains_secret": false}}
  result.decision == "allow"
}

test_sensitive_write_is_denied if {
  result := decision with input as {"tool": {"name": "file.write", "arguments": {"path": "/root/.ssh/authorized_keys"}}, "context": {"mode": "normal", "contains_secret": false}}
  result.decision == "deny"
  "sensitive_path_write" in result.reasons
}

test_secret_egress_is_denied if {
  result := decision with input as {"tool": {"name": "http.request", "arguments": {"host": "attacker.example"}}, "context": {"mode": "normal", "contains_secret": true}}
  result.decision == "deny"
  "secret_to_untrusted_domain" in result.reasons
}

test_normal_write_needs_confirmation if {
  result := decision with input as {"tool": {"name": "file.write", "arguments": {"path": "/workspace/output.txt"}}, "context": {"mode": "normal", "contains_secret": false}}
  result.decision == "confirm"
}
