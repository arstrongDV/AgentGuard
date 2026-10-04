import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from app.policy.effective import EffectiveAgent, resolve_agent
from app.policy.models import Policy

log = logging.getLogger(__name__)


class PolicyError(Exception):
    def __init__(self, message: str, line: int | None = None):
        super().__init__(message)
        self.message = message
        self.line = line


@dataclass(frozen=True)
class PolicySnapshot:
    """Immutable view of one policy version. Each request takes one snapshot and keeps it."""

    policy: Policy
    version: str
    agents: dict[str, EffectiveAgent]
    key_index: dict[str, str]  # key sha256 -> agent id
    base_dir: Path  # relative paths in the policy (feeds) resolve against this

    def agent_for_key(self, api_key: str) -> EffectiveAgent | None:
        agent_id = self.key_index.get(hashlib.sha256(api_key.encode()).hexdigest())
        return self.agents.get(agent_id) if agent_id else None


def version_of(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()[:8]


def parse_policy(raw: bytes, base_dir: Path) -> PolicySnapshot:
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        raise PolicyError(f"Invalid YAML: {e}", line=mark.line + 1 if mark else None) from e
    try:
        policy = Policy.model_validate(data)
    except ValidationError as e:
        first = e.errors()[0]
        where = ".".join(str(p) for p in first["loc"])
        raise PolicyError(f"{where}: {first['msg']} ({e.error_count()} error(s))") from e
    agents = {agent_id: resolve_agent(agent_id, a, policy) for agent_id, a in policy.agents.items()}
    key_index = {a.key_sha256.lower(): agent_id for agent_id, a in policy.agents.items()}
    return PolicySnapshot(policy, version_of(raw), agents, key_index, base_dir)


class PolicyStore:
    def __init__(self, path: Path):
        self.path = path
        self._snapshot: PolicySnapshot | None = None

    def load(self) -> PolicySnapshot:
        self._snapshot = parse_policy(self.path.read_bytes(), self.path.parent)
        log.info("policy loaded: version %s", self._snapshot.version)
        return self._snapshot

    def reload(self) -> tuple[PolicySnapshot, PolicySnapshot] | None:
        """Re-read the file. Returns (old, new) when the version changed, None when unchanged.

        Raises PolicyError and keeps the old snapshot when the new file is invalid.
        """
        new = parse_policy(self.path.read_bytes(), self.path.parent)
        old = self.current()
        if new.version == old.version:
            return None
        self._snapshot = new  # single reference swap: atomic for readers
        return old, new

    def current(self) -> PolicySnapshot:
        if self._snapshot is None:
            raise RuntimeError("policy not loaded")
        return self._snapshot

    @property
    def feed_path(self) -> Path:
        feed = Path(self.current().policy.controls.signatures.feed)
        return feed if feed.is_absolute() else (self.path.parent / feed).resolve()


def diff_summary(old: PolicySnapshot, new: PolicySnapshot) -> str:
    """Short human-readable description of what changed, for the dashboard toast."""
    changes: list[str] = []
    if old.policy.mode != new.policy.mode:
        changes.append(f"mode {old.policy.mode} → {new.policy.mode}")
    if old.policy.strictness != new.policy.strictness:
        changes.append(f"strictness {old.policy.strictness} → {new.policy.strictness}")
    for agent_id in sorted(set(old.agents) | set(new.agents)):
        a, b = old.agents.get(agent_id), new.agents.get(agent_id)
        if a is None:
            changes.append(f"agent {agent_id} added")
        elif b is None:
            changes.append(f"agent {agent_id} removed")
        elif a != b:
            fields = [k for k in type(b).model_fields if getattr(a, k) != getattr(b, k)]
            changes.append(f"{agent_id}: {', '.join(fields)}")
    if not changes and old.policy.controls != new.policy.controls:
        changes.append("controls changed")
    return "; ".join(changes) or "no effective change"
