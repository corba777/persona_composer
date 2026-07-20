"""Module and manifest data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ModuleType(str, Enum):
    IDENTITY = "identity"
    ROLE = "role"
    TRAIT = "trait"
    SPEECH = "speech"
    RELATIONSHIP = "relationship"
    OUTPUT_RULES = "output_rules"


class Priority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    @property
    def rank(self) -> int:
        return {Priority.HIGH: 3, Priority.MEDIUM: 2, Priority.LOW: 1}[self]


class Adaptation(str, Enum):
    AS_IS = "as-is"
    EXTRACTED = "extracted"


class SpeechMode(str, Enum):
    PROMPT = "prompt"
    REWRITER = "rewriter"


SKELETON_VERSION = "2"

# Convenience default when callers want the old always-on text via SkeletonConfig.
DEFAULT_OUTPUT_RULES = (
    "Follow the sections above. Prefer concrete actions over vague intent."
)


@dataclass(frozen=True)
class SkeletonConfig:
    """Skeleton knobs not derived from modules.

    ``output_rules`` is a fallback when no ``type: output_rules`` module is active.
    Empty string = omit the ``<output_rules>`` slot (unless a module provides it).
    """

    version: str = SKELETON_VERSION
    output_rules: str = ""


@dataclass
class Module:
    """A parsed module ready for composition."""

    path: Path
    type: ModuleType
    name: str
    body: str
    hash: str
    # trait
    priority: Priority | None = None
    conflicts: list[str] = field(default_factory=list)
    # role
    tools: list[str] = field(default_factory=list)
    # speech
    mode: SpeechMode = SpeechMode.PROMPT
    # relationship
    agent: str | None = None
    status: str | None = None
    # import / provenance
    source: str | None = None
    adaptation: Adaptation | None = None
    origin: str | None = None
    source_path: Path | None = None
    source_hash: str | None = None
    source_body: str | None = None

    @property
    def render_body(self) -> str:
        """Body inserted into the XML slot (respects adaptation)."""
        if self.adaptation == Adaptation.AS_IS:
            return self.source_body or ""
        return self.body

    @property
    def is_imported(self) -> bool:
        return self.source is not None


@dataclass
class ConflictResolution:
    winner: str
    loser: str
    winner_priority: str
    loser_priority: str

    def to_line(self) -> str:
        return (
            f"When {self.winner} and {self.loser} conflict, "
            f"{self.winner} (priority={self.winner_priority}) governs; "
            f"{self.loser} yields."
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "winner": self.winner,
            "loser": self.loser,
            "winner_priority": self.winner_priority,
            "loser_priority": self.loser_priority,
            "rule": self.to_line(),
        }


@dataclass
class ManifestModule:
    path: str
    type: str
    name: str
    hash: str
    source: str | None = None
    source_hash: str | None = None
    origin: str | None = None
    adaptation: str | None = None
    mode: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "path": self.path,
            "type": self.type,
            "name": self.name,
            "hash": self.hash,
        }
        if self.source is not None:
            data["source"] = self.source
        if self.source_hash is not None:
            data["source_hash"] = self.source_hash
        if self.origin is not None:
            data["origin"] = self.origin
        if self.adaptation is not None:
            data["adaptation"] = self.adaptation
        if self.mode is not None:
            data["mode"] = self.mode
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ManifestModule:
        return cls(
            path=data["path"],
            type=data["type"],
            name=data["name"],
            hash=data["hash"],
            source=data.get("source"),
            source_hash=data.get("source_hash"),
            origin=data.get("origin"),
            adaptation=data.get("adaptation"),
            mode=data.get("mode"),
        )


@dataclass
class Manifest:
    skeleton_version: str
    timestamp: str
    modules: list[ManifestModule]
    conflict_rules: list[dict[str, str]] = field(default_factory=list)
    rewriter_stack: list[ManifestModule] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "skeleton_version": self.skeleton_version,
            "timestamp": self.timestamp,
            "modules": [m.to_dict() for m in self.modules],
            "conflict_rules": self.conflict_rules,
            "rewriter_stack": [m.to_dict() for m in self.rewriter_stack],
            "warnings": self.warnings,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Manifest:
        return cls(
            skeleton_version=data["skeleton_version"],
            timestamp=data["timestamp"],
            modules=[ManifestModule.from_dict(m) for m in data.get("modules", [])],
            conflict_rules=list(data.get("conflict_rules", [])),
            rewriter_stack=[
                ManifestModule.from_dict(m) for m in data.get("rewriter_stack", [])
            ],
            warnings=list(data.get("warnings", [])),
        )
