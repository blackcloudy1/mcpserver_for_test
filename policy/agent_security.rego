package agent_security

import rego.v1

side_effect_tools := {"file.write", "shell.exec", "http.request", "git.push", "agent.spawn"}
trusted_domains := {"localhost", "127.0.0.1", "docs-server", "sales-server", "report-server", "mock-egress"}

deny_reasons contains "sensitive_path_write" if {
  input.tool.name == "file.write"
  regex.match(`(?i)(/etc/|/root/|\.ssh/|\.aws/|\.env$)`, object.get(input.tool.arguments, "path", ""))
}

deny_reasons contains "secret_to_untrusted_domain" if {
  input.tool.name == "http.request"
  input.context.contains_secret
  host := object.get(input.tool.arguments, "host", "")
  not host in trusted_domains
}

deny_reasons contains "download_pipe_execute" if {
  input.tool.name == "shell.exec"
  command := lower(object.get(input.tool.arguments, "command", ""))
  regex.match(`(curl|wget).*(\||;|&&).*(sh|bash|python|powershell)`, command)
}

deny_reasons contains "decode_then_execute" if {
  input.tool.name == "shell.exec"
  command := lower(object.get(input.tool.arguments, "command", ""))
  regex.match(`(base64|frombase64string).*(sh|bash|python|powershell|invoke-expression|iex)`, command)
}

deny_reasons contains "write_in_read_only_session" if {
  input.context.mode == "read_only"
  input.tool.name == "git.push"
}

deny_reasons contains "secret_delegation" if {
  input.tool.name == "agent.spawn"
  input.context.contains_secret
}

default decision := {"decision": "deny", "risk": "high", "reasons": ["policy_input_invalid"]}

decision := {"decision": "deny", "risk": "high", "reasons": sort(reasons)} if {
  reasons := [reason | some reason in deny_reasons]
  count(reasons) > 0
}

decision := {"decision": "allow", "risk": "low", "reasons": []} if {
  count(deny_reasons) == 0
  not input.tool.name in side_effect_tools
}

decision := {"decision": "confirm", "risk": "medium", "reasons": ["side_effect_requires_confirmation"]} if {
  count(deny_reasons) == 0
  input.tool.name in side_effect_tools
}
