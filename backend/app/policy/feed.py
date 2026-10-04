"""Historical attack signature feed (feeds/signatures.json), loaded from a file and hot-reloaded."""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.core.decision import Severity

log = logging.getLogger(__name__)

Stage = Literal["llm_in", "llm_out", "mcp_call", "mcp_result"]
ALL_STAGES: list[Stage] = ["llm_in", "llm_out", "mcp_call", "mcp_result"]


class Signature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    category: str
    severity: Severity
    pattern: str
    applies_to: list[Stage] = ALL_STAGES
    action: Literal["block", "redact", "allow"] = "block"
    case_sensitive: bool = False
    match_on: Literal["normalized", "raw"] = "normalized"
    description: str = ""


class FeedFile(BaseModel):
    version: str
    signatures: list[Signature]


@dataclass(frozen=True)
class CompiledSignature:
    sig: Signature
    regex: re.Pattern[str]


@dataclass(frozen=True)
class SignatureFeed:
    version: str
    by_stage: dict[str, list[CompiledSignature]]
    count: int


EMPTY_FEED = SignatureFeed(version="none", by_stage={s: [] for s in ALL_STAGES}, count=0)


def load_feed(path: Path) -> SignatureFeed:
    return parse_feed(path.read_text(encoding="utf-8"))


def parse_feed(text: str) -> SignatureFeed:
    data = FeedFile.model_validate(json.loads(text))
    by_stage: dict[str, list[CompiledSignature]] = {s: [] for s in ALL_STAGES}
    for sig in data.signatures:
        flags = 0 if sig.case_sensitive else re.IGNORECASE
        compiled = CompiledSignature(sig, re.compile(sig.pattern, flags))
        for stage in sig.applies_to:
            by_stage[stage].append(compiled)
    log.info("signature feed %s loaded: %d signatures", data.version, len(data.signatures))
    return SignatureFeed(version=data.version, by_stage=by_stage, count=len(data.signatures))
