"""Download the ML models AgentGuard runs locally (no paid APIs, no runtime downloads).

    python scripts/download_models.py            # into backend/models/
    python scripts/download_models.py --verify   # only print/verify SHA-256 of what is there

Prompt-injection classifier: protectai/deberta-v3-base-prompt-injection-v2 (Apache-2.0), ONNX export, so the
gateway needs onnxruntime + tokenizers, not PyTorch. Pin the printed sha256 in policy.yaml (supply_chain.pinned).
"""

import argparse
import hashlib
import sys
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parents[1] / "models"
INJECTION_REPO = "protectai/deberta-v3-base-prompt-injection-v2"
INJECTION_REVISION = "main"
FILES = ["onnx/model.onnx", "onnx/tokenizer.json", "onnx/config.json"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def target_dir() -> Path:
    return MODELS_DIR / INJECTION_REPO.replace("/", "__")


def download() -> None:
    from huggingface_hub import hf_hub_download

    out = target_dir()
    for name in FILES:
        hf_hub_download(INJECTION_REPO, name, revision=INJECTION_REVISION, local_dir=out)
        print(f"  {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if not args.verify:
        print(f"downloading {INJECTION_REPO} -> {target_dir()}")
        download()
    model = target_dir() / "onnx" / "model.onnx"
    if not model.exists():
        print("model not found; run without --verify", file=sys.stderr)
        return 1
    print(f"{INJECTION_REPO}: model.onnx sha256 {sha256(model)}  ({model.stat().st_size / 1e6:.0f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
