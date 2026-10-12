# models/ — dedicated offline model folder

All offline models live here and **only** here. THANS never writes anywhere
else and never needs the internet once these files exist.

| File / folder | Used for | Size | Required? |
|---------------|----------|------|-----------|
| `vosk-model-small-en-us-0.15/` | Speech recognition (voice commands) | ≈ 40 MB | for voice input |
| `Qwen2.5-0.5B-Instruct-Q4_K_M.gguf` | Optional tiny LLM (free-form commands) | ≈ 408 MB | optional (off by default) |

## Get the models

```bash
python scripts/download_models.py            # both, with progress bars
python scripts/download_models.py --only stt # just speech recognition
python scripts/download_models.py --only llm # just the LLM
python scripts/download_models.py --list     # show LLM choices
```

### LLM choices (`--model NAME`)

| NAME | File | Size | Notes |
|------|------|------|-------|
| `qwen2.5-0.5b` *(default)* | `qwen2.5-0.5b-instruct-q4_k_m.gguf` | ≈ 408 MB | best tiny JSON parser |
| `qwen2.5-1.5b` | `qwen2.5-1.5b-instruct-q4_k_m.gguf` | ≈ 1.0 GB | more robust phrasing |
| `llama3.2-1b` | `llama-3.2-1b-instruct-q4_k_m.gguf` | ≈ 760 MB | Llama 3.2 family |

The LLM is **optional**: the built-in rule parser (0 MB) handles every command
in the README reference. Enable it in Settings → "Use offline LLM".

## You may also drop in other GGUF files

Any `.gguf` placed here shows up in Settings → LLM model picker.
