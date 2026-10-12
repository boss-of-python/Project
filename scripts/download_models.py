#!/usr/bin/env python3
"""One-time downloader for THANS offline models (stdlib only).

Downloads into the dedicated ``models/`` folder:
  * STT  - Vosk small EN-US model (zip, extracted)
  * LLM  - a small GGUF file for llama.cpp (optional, off by default)

Usage:
    python scripts/download_models.py                 # STT + default LLM
    python scripts/download_models.py --only stt      # speech only (~40 MB)
    python scripts/download_models.py --only llm      # LLM only
    python scripts/download_models.py --model llama3.2-1b
    python scripts/download_models.py --list          # list LLM choices
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

try:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from thans import config
except Exception:  # pragma: no cover - run from anywhere
    config = None

DEFAULT_DIR = Path(__file__).resolve().parent.parent / "models"

STT = {
    "name": "vosk-model-small-en-us-0.15",
    "url": "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
    "size_mb": 40,
}

LLM_CATALOG = {
    "qwen2.5-0.5b": {
        "file": "qwen2.5-0.5b-instruct-q4_k_m.gguf",
        "url": "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf",
        "size_mb": 408,
        "default": True,
    },
    "qwen2.5-1.5b": {
        "file": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "url": "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "size_mb": 1027,
    },
    "llama3.2-1b": {
        "file": "llama-3.2-1b-instruct-q4_k_m.gguf",
        "url": "https://huggingface.co/unsloth/llama-3.2-1B-GGUF/resolve/main/llama-3.2-1b-instruct-q4_k_m.gguf",
        "size_mb": 758,
    },
}

CHUNK = 1024 * 256


def _bar(done: int, total: int, width: int = 30) -> str:
    frac = (done / total) if total else 1.0
    filled = int(width * frac)
    return f"[{'#' * filled}{'.' * (width - filled)}] {frac * 100:5.1f}%"


def download(url: str, dest: Path, label: str) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  = {label}: already present ({dest.name}) - skipping")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  ↓ {label}: {url}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "THANS-downloader/0.1"})
        with urllib.request.urlopen(req, timeout=60) as r:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            with open(tmp, "wb") as f:
                while True:
                    chunk = r.read(CHUNK)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        print(f"\r    {_bar(done, total)} {done // 1048576} / {total // 1048576} MB", end="", flush=True)
        print()
        shutil.move(tmp, dest)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _vosk_ready(target: Path) -> bool:
    try:
        from thans.model_manager import vosk_model_ready
        return vosk_model_ready(target)
    except Exception:
        return (target / "am" / "final.mdl").exists() or (target / "model.bin").exists()


def fetch_stt(models_dir: Path, force: bool) -> None:
    target = models_dir / STT["name"]
    if _vosk_ready(target) and not force:
        print(f"  = STT model: already present ({target.name}) - skipping")
        return
    zip_path = models_dir / (STT["name"] + ".zip")
    if zip_path.exists() and not force:
        pass  # reuse existing zip
    else:
        download(STT["url"], zip_path, "STT model (Vosk small EN-US, ~40 MB)")
    print("  … extracting STT model")
    if target.exists():
        shutil.rmtree(target)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(models_dir)
    zip_path.unlink(missing_ok=True)
    if not _vosk_ready(target):
        sys.exit(f"ERROR: extraction did not produce a Vosk model at {target}")
    print(f"  ✓ STT model ready: {target.name}/")


def fetch_llm(models_dir: Path, name: str, force: bool) -> None:
    spec = LLM_CATALOG[name]
    dest = models_dir / spec["file"]
    download(spec["url"], dest, f"LLM model ({name}, ~{spec['size_mb']} MB)")
    print(f"  ✓ LLM model ready: {dest.name}")
    if config is not None:
        cfg = config.load_config()
        if cfg.get("llm_model") != spec["file"]:
            cfg["llm_model"] = spec["file"]
            config.save_config(cfg)
            print(f"  … default LLM in config set to {spec['file']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", choices=["stt", "llm"], help="download just one part")
    ap.add_argument("--model", default=None, help=f"LLM choice: {', '.join(LLM_CATALOG)}")
    ap.add_argument("--dir", default=str(DEFAULT_DIR), help="models folder (default: ./models)")
    ap.add_argument("--force", action="store_true", help="re-download even if present")
    ap.add_argument("--list", action="store_true", help="list LLM choices and exit")
    a = ap.parse_args(argv)

    if a.list:
        print("Available LLM models:")
        for name, spec in LLM_CATALOG.items():
            tag = " (default)" if spec.get("default") else ""
            print(f"  {name:<14} {spec['file']}  ~{spec['size_mb']} MB{tag}")
        return 0

    models_dir = Path(a.dir).expanduser().resolve()
    models_dir.mkdir(parents=True, exist_ok=True)
    llm_name = a.model or next(n for n, s in LLM_CATALOG.items() if s.get("default"))
    if llm_name not in LLM_CATALOG:
        sys.exit(f"ERROR: unknown --model '{llm_name}'. Use --list.")

    print(f"THANS offline model downloader → {models_dir}")
    if a.only in (None, "stt"):
        fetch_stt(models_dir, a.force)
    if a.only in (None, "llm"):
        fetch_llm(models_dir, llm_name, a.force)

    print("\nDone. THANS now runs 100% offline:")
    print("    python -m thans")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
