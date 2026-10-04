"""Semantic layer: the models behind tiers T2 (injection classifier) and T3 (LLM judge).

Both are optional. When a model is missing the gateway keeps working on the deterministic tiers and
the pipeline records why the semantic check was skipped.
"""

from dataclasses import dataclass

from app.ml.injection import InjectionClassifier
from app.ml.judge import LlmJudge


@dataclass
class MLRuntime:
    classifier: InjectionClassifier | None
    judge: LlmJudge | None
