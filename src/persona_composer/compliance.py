"""Optional compliance gate for composed prompts / skill Markdown.

Deterministic pattern rules only — no LLM. Off by default; when enabled,
compose/skill export fail with ValidationError listing violated rules.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from persona_composer.errors import ValidationError
from persona_composer.hashing import file_hash
from persona_composer.parse import split_frontmatter

DEFAULT_COMPLIANCE_NAME = "Default"

# Built-in ruleset (also editable in the playground). Patterns are case-insensitive
# where marked (?i). Aimed at common skill/prompt footguns, not a full security audit.
DEFAULT_COMPLIANCE_MD = """\
---
type: compliance
name: Default
rules:
  - id: no-bash-c
    pattern: '(?i)\\b(?:ba)?sh\\s+-c\\b'
    message: Must not instruct invoking an arbitrary shell via sh/bash -c
  - id: no-curl-pipe-shell
    pattern: '(?i)(?:curl|wget)\\b[^\\n]*\\|\\s*(?:ba)?sh\\b'
    message: Must not pipe remote download output into a shell
  - id: no-powershell-encoded
    pattern: '(?i)powershell[^\\n]*-(?:enc|encodedcommand)\\b'
    message: Must not instruct PowerShell encoded-command execution
  - id: no-rm-rf-root
    pattern: '(?i)\\brm\\s+-[a-z]*r[a-z]*f?[a-z]*\\s+/(?:\\s|$)|\\brm\\s+-[a-z]*f[a-z]*r[a-z]*\\s+/'
    message: Must not instruct destructive rm against filesystem roots
  - id: no-exfil-webhook
    pattern: '(?i)(?:curl|wget|fetch)\\b[^\\n]*(?:webhook|discord\\.com/api/webhooks|hooks\\.slack\\.com)'
    message: Must not instruct exfiltrating data to webhooks / chat hooks
  - id: no-ignore-safety
    pattern: '(?i)ignore\\s+(?:all\\s+)?(?:previous|prior|above)\\s+(?:instructions|rules|safety)|disregard\\s+(?:safety|guardrails|compliance)'
    message: Must not instruct ignoring safety / compliance / prior system rules
---
Default compliance pack for persona_composer. Edit or replace with a custom
compliance Markdown file. Rules are regexes applied to the compiled artifact
(XML prompt and/or skill Markdown). Matching is a **build error**.
"""


@dataclass(frozen=True)
class ComplianceRule:
    id: str
    pattern: str
    message: str

    def compile(self) -> re.Pattern[str]:
        try:
            return re.compile(self.pattern)
        except re.error as exc:
            raise ValidationError(
                f"compliance rule {self.id!r}: invalid regex: {exc}"
            ) from exc


@dataclass
class ComplianceViolation:
    rule_id: str
    message: str
    excerpt: str = ""

    def to_dict(self) -> dict[str, str]:
        data = {"rule_id": self.rule_id, "message": self.message}
        if self.excerpt:
            data["excerpt"] = self.excerpt
        return data

    def format_line(self) -> str:
        if self.excerpt:
            return (
                f"compliance[{self.rule_id}]: {self.message} "
                f"(matched: {self.excerpt!r})"
            )
        return f"compliance[{self.rule_id}]: {self.message}"


@dataclass
class ComplianceRuleset:
    name: str
    rules: list[ComplianceRule] = field(default_factory=list)
    source: str | None = None  # path or "builtin:Default"
    rules_hash: str = ""

    def to_manifest_meta(self) -> dict[str, Any]:
        return {
            "checked": True,
            "ruleset": self.name,
            "rules_hash": self.rules_hash,
            "source": self.source,
            "rule_ids": [r.id for r in self.rules],
        }


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def default_compliance_md() -> str:
    return DEFAULT_COMPLIANCE_MD


def default_compliance_ruleset() -> ComplianceRuleset:
    return parse_compliance_md(DEFAULT_COMPLIANCE_MD, source="builtin:Default")


def parse_compliance_md(text: str, *, source: str | None = None) -> ComplianceRuleset:
    """Parse compliance Markdown (frontmatter rules: and/or ### body sections)."""
    text = text.strip()
    if not text:
        raise ValidationError("compliance rules Markdown is empty")

    name = DEFAULT_COMPLIANCE_NAME
    rules: list[ComplianceRule] = []
    body = text

    if text.startswith("---"):
        try:
            fm, body = split_frontmatter(text + ("\n" if not text.endswith("\n") else ""))
        except ValidationError:
            # Allow body-only documents without frontmatter
            fm, body = {}, text
        else:
            if fm.get("type") not in (None, "compliance"):
                raise ValidationError(
                    f"compliance file type must be 'compliance', got {fm.get('type')!r}"
                )
            if fm.get("name"):
                name = str(fm["name"]).strip() or name
            raw_rules = fm.get("rules")
            if raw_rules is not None:
                if not isinstance(raw_rules, list):
                    raise ValidationError("compliance frontmatter 'rules' must be a list")
                for i, item in enumerate(raw_rules):
                    rules.append(_rule_from_mapping(item, index=i))

    body_rules = _parse_body_rule_sections(body)
    # Body sections extend / override same ids
    by_id = {r.id: r for r in rules}
    for r in body_rules:
        by_id[r.id] = r
    rules = list(by_id.values())

    if not rules:
        raise ValidationError(
            "compliance ruleset has no rules "
            "(add frontmatter rules: or ### id sections with pattern:/message:)"
        )

    # Validate regexes early
    for r in rules:
        r.compile()

    return ComplianceRuleset(
        name=name,
        rules=rules,
        source=source,
        rules_hash=_hash_text(
            "\n".join(f"{r.id}\n{r.pattern}\n{r.message}" for r in rules)
        ),
    )


def _rule_from_mapping(item: Any, *, index: int) -> ComplianceRule:
    if not isinstance(item, dict):
        raise ValidationError(f"compliance rules[{index}] must be a mapping")
    rid = str(item.get("id") or "").strip()
    pattern = str(item.get("pattern") or "").strip()
    message = str(item.get("message") or "").strip()
    if not rid or not pattern or not message:
        raise ValidationError(
            f"compliance rules[{index}] requires non-empty id, pattern, and message"
        )
    return ComplianceRule(id=rid, pattern=pattern, message=message)


_SECTION_RE = re.compile(
    r"^###\s+(?P<id>[A-Za-z0-9_.:-]+)\s*$",
    re.MULTILINE,
)


def _parse_body_rule_sections(body: str) -> list[ComplianceRule]:
    body = (body or "").strip()
    if not body:
        return []
    matches = list(_SECTION_RE.finditer(body))
    if not matches:
        return []
    rules: list[ComplianceRule] = []
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        block = body[start:end].strip()
        rid = match.group("id")
        pattern = _field_from_block(block, "pattern")
        message = _field_from_block(block, "message")
        if not pattern or not message:
            raise ValidationError(
                f"compliance section ### {rid} needs pattern: and message: lines"
            )
        rules.append(ComplianceRule(id=rid, pattern=pattern, message=message))
    return rules


def _field_from_block(block: str, key: str) -> str:
    # pattern: ...  or pattern: |\n  multiline
    line_re = re.compile(
        rf"^{re.escape(key)}\s*:\s*(?P<val>.+)\s*$",
        re.MULTILINE | re.IGNORECASE,
    )
    m = line_re.search(block)
    if not m:
        return ""
    val = m.group("val").strip()
    if val in ("|", ">"):
        # remainder after this line
        after = block[m.end() :]
        lines = []
        for line in after.splitlines():
            if re.match(r"^[A-Za-z_][\w-]*\s*:", line):
                break
            lines.append(line)
        return "\n".join(lines).strip()
    # strip optional quotes
    if (val.startswith("'") and val.endswith("'")) or (
        val.startswith('"') and val.endswith('"')
    ):
        val = val[1:-1]
    return val


def load_compliance_ruleset(path: Path | str) -> ComplianceRuleset:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    rs = parse_compliance_md(text, source=str(path))
    # Prefer file hash for provenance when loaded from disk
    rs.rules_hash = file_hash(path)
    return rs


def resolve_compliance_ruleset(
    compliance: bool | Path | str | ComplianceRuleset | None,
) -> ComplianceRuleset | None:
    """
    Normalize compose/skill ``compliance=`` argument.

    - ``None`` / ``False`` → disabled
    - ``True`` → builtin Default
    - ``Path`` / existing path string → load file
    - other ``str`` → parse as Markdown text
    - ``ComplianceRuleset`` → as-is
    """
    if compliance is None or compliance is False:
        return None
    if compliance is True:
        return default_compliance_ruleset()
    if isinstance(compliance, ComplianceRuleset):
        return compliance
    if isinstance(compliance, Path):
        return load_compliance_ruleset(compliance)
    if isinstance(compliance, str):
        # Inline Markdown (playground textarea) must not hit the filesystem:
        # Path(long_md).is_file() raises ENAMETOOLONG (errno 63) on macOS.
        if "\n" not in compliance:
            candidate = Path(compliance)
            try:
                if candidate.is_file():
                    return load_compliance_ruleset(candidate)
            except OSError:
                pass
        return parse_compliance_md(compliance, source="inline")
    raise ValidationError(
        f"compliance must be bool | Path | str | ComplianceRuleset, got {type(compliance)!r}"
    )


def check_compliance(
    text: str,
    ruleset: ComplianceRuleset,
) -> list[ComplianceViolation]:
    """Return all violations (empty = pass)."""
    violations: list[ComplianceViolation] = []
    for rule in ruleset.rules:
        cre = rule.compile()
        for match in cre.finditer(text or ""):
            excerpt = match.group(0)
            if len(excerpt) > 120:
                excerpt = excerpt[:117] + "..."
            violations.append(
                ComplianceViolation(
                    rule_id=rule.id,
                    message=rule.message,
                    excerpt=excerpt,
                )
            )
            break  # one hit per rule is enough for the error report
    return violations


def enforce_compliance(
    text: str,
    ruleset: ComplianceRuleset,
    *,
    artifact: str = "composed prompt",
) -> None:
    """Raise ValidationError if any rule matches."""
    violations = check_compliance(text, ruleset)
    if not violations:
        return
    lines = [
        f"compliance check failed for {artifact} "
        f"(ruleset={ruleset.name!r}, source={ruleset.source!r})"
    ]
    lines.extend(v.format_line() for v in violations)
    raise ValidationError(lines[0], errors=lines)