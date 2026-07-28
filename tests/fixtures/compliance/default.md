---
type: compliance
name: Default
rules:
  - id: no-bash-c
    pattern: '(?i)\b(?:ba)?sh\s+-c\b'
    message: Must not instruct invoking an arbitrary shell via sh/bash -c
  - id: no-curl-pipe-shell
    pattern: '(?i)(?:curl|wget)\b[^\n]*\|\s*(?:ba)?sh\b'
    message: Must not pipe remote download output into a shell
  - id: no-powershell-encoded
    pattern: '(?i)powershell[^\n]*-(?:enc|encodedcommand)\b'
    message: Must not instruct PowerShell encoded-command execution
  - id: no-rm-rf-root
    pattern: '(?i)\brm\s+-[a-z]*r[a-z]*f?[a-z]*\s+/(?:\s|$)|\brm\s+-[a-z]*f[a-z]*r[a-z]*\s+/'
    message: Must not instruct destructive rm against filesystem roots
  - id: no-exfil-webhook
    pattern: '(?i)(?:curl|wget|fetch)\b[^\n]*(?:webhook|discord\.com/api/webhooks|hooks\.slack\.com)'
    message: Must not instruct exfiltrating data to webhooks / chat hooks
  - id: no-ignore-safety
    pattern: '(?i)ignore\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions|rules|safety)|disregard\s+(?:safety|guardrails|compliance)'
    message: Must not instruct ignoring safety / compliance / prior system rules
---
Default compliance pack for persona_composer. Edit or replace with a custom
compliance Markdown file. Rules are regexes applied to the compiled artifact
(XML prompt and/or skill Markdown). Matching is a **build error**.
