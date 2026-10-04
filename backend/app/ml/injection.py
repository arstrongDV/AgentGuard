"""T2: prompt-injection classifier, protectai/deberta-v3-base-prompt-injection-v2 (Apache-2.0).

Runs the ONNX export on onnxruntime (CPU) with the `tokenizers` library: no PyTorch in the image.
Loaded in a background thread at startup so the gateway is available immediately.
"""

import hashlib
import json
import logging
import threading
from pathlib import Path
from typing import Literal

log = logging.getLogger(__name__)

MAX_TOKENS = 512
WINDOW_CHARS = 1600  # long texts (tool results) are scored in overlapping windows; the max wins
WINDOW_OVERLAP = 300

Status = Literal["disabled", "loading", "loaded", "unavailable"]


class InjectionClassifier:
    def __init__(self, model_dir: Path, pinned_sha256: str | None = None, threads: int = 2):
        self.model_dir = model_dir
        self.pinned_sha256 = pinned_sha256
        self.threads = threads
        self.status: Status = "loading"
        self.detail = ""
        self._session = None
        self._tokenizer = None
        self._inputs: list[str] = []
        self._injection_index = 1
        self._lock = threading.Lock()

    @property
    def ready(self) -> bool:
        return self.status == "loaded"

    def load(self) -> None:
        """Blocking. Call from a worker thread. Never raises: failures leave status 'unavailable'."""
        try:
            self._load()
            self.status = "loaded"
            log.info("injection classifier loaded from %s", self.model_dir)
        except Exception as e:  # missing files, bad hash, missing onnxruntime...
            self.status = "unavailable"
            self.detail = str(e)
            log.warning("injection classifier unavailable (deterministic tiers still active): %s", e)

    def _load(self) -> None:
        onnx_dir = self.model_dir / "onnx"
        model_path = onnx_dir / "model.onnx"
        if not model_path.exists():
            raise FileNotFoundError(f"{model_path} not found; run `make models`")
        if self.pinned_sha256:
            actual = _sha256(model_path)
            if actual != self.pinned_sha256.lower():
                # supply-chain control: never load a model file that is not the one we pinned
                raise ValueError(f"sha256 mismatch for {model_path.name}: expected {self.pinned_sha256[:12]}…, got {actual[:12]}…")

        import onnxruntime as ort
        from tokenizers import Tokenizer

        options = ort.SessionOptions()
        options.intra_op_num_threads = self.threads
        self._session = ort.InferenceSession(str(model_path), sess_options=options, providers=["CPUExecutionProvider"])
        self._inputs = [i.name for i in self._session.get_inputs()]
        tokenizer = Tokenizer.from_file(str(onnx_dir / "tokenizer.json"))
        tokenizer.enable_truncation(max_length=MAX_TOKENS)
        self._tokenizer = tokenizer
        labels = json.loads((onnx_dir / "config.json").read_text()).get("id2label", {})
        self._injection_index = next((int(i) for i, name in labels.items() if name.upper() == "INJECTION"), 1)

    def score(self, text: str) -> float:
        """P(injection) for one text, max over windows. Blocking; call via asyncio.to_thread."""
        return max(self._score_window(w) for w in _windows(text))

    def score_many(self, texts: list[str]) -> list[float]:
        return [self.score(t) for t in texts]

    def _score_window(self, text: str) -> float:
        import numpy as np

        assert self._session is not None and self._tokenizer is not None
        encoding = self._tokenizer.encode(text)
        ids = np.array([encoding.ids], dtype=np.int64)
        feeds = {"input_ids": ids, "attention_mask": np.array([encoding.attention_mask], dtype=np.int64)}
        if "token_type_ids" in self._inputs:
            feeds["token_type_ids"] = np.zeros_like(ids)
        logits = self._session.run(None, {k: v for k, v in feeds.items() if k in self._inputs})[0][0]
        exp = np.exp(logits - logits.max())
        return float(exp[self._injection_index] / exp.sum())


def _windows(text: str) -> list[str]:
    if len(text) <= WINDOW_CHARS:
        return [text]
    step = WINDOW_CHARS - WINDOW_OVERLAP
    return [text[i : i + WINDOW_CHARS] for i in range(0, len(text) - WINDOW_OVERLAP, step)]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
