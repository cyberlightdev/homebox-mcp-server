# Inventory Voice Assistant

A hands-free, locally-hosted voice interface for [Homebox](https://github.com/sysadminsmedia/homebox). Speak to catalogue items as you physically sort through bins and boxes — no typing, no clicking. Everything runs on your own hardware; nothing leaves your network.

## How it works

You talk. The assistant transcribes your speech (Whisper), understands your intent (a local LLM via llama.cpp), updates Homebox via its REST API, and reads back exactly what changed (Kokoro TTS). A small FastAPI service wires it all together and serves the single-page UI.

```
Browser ──▶ inventory-api ──▶ Whisper  (speech → text)
                          ──▶ llama.cpp (text → tool calls)
                          ──▶ Homebox  (inventory writes)
                          ──▶ Kokoro   (text → speech)
```

Sessions are stateful: the assistant remembers your current location and maintains an undo stack so mistakes are easy to fix.

---

## Prerequisites

- **Docker Compose** with the Docker Compose plugin (`docker compose`)
- **NVIDIA GPU** — whisper and llama.cpp both use CUDA. The `nvidia-container-toolkit` must be installed and working (`docker run --gpus all nvidia/cuda:12-base nvidia-smi` should succeed)
- A running **Homebox** instance (included in the compose file, or point at an existing one)
- A **GGUF model file** with tool-calling support — see [Model selection](#model-selection) below

---

## Quick start

### 1. Clone and configure

```bash
git clone https://github.com/cyberlightdev/inventory-voice-assistant
cd inventory-voice-assistant
cp .env.example .env
```

Edit `.env`:

```env
HOMEBOX_EMAIL=you@example.com
HOMEBOX_PASSWORD=your-password
LLAMA_CPP_MODEL=model.gguf   # filename only — file must be in the repo root
MMPROJ_MODEL=                # optional: mmproj GGUF for vision support
WHISPER_MODEL=small          # tiny | base | small | medium | large-v3
KOKORO_VOICE=af_sky          # see Voice options below
HISTORY_TURNS=6              # conversation turns kept in context
```

### 2. Place your model file

Drop your GGUF file(s) in the repo root (same directory as `docker-compose.yml`). The compose file mounts `.:/models` so llama.cpp can find them.

### 3. Start

```bash
docker compose up -d
```

Open **http://localhost:4004** in your browser. Grant microphone permission when prompted.

---

## Using the pre-built image

Tagged releases are published to GHCR automatically. To use the pre-built `inventory-api` image instead of building locally, replace the `build:` line in `docker-compose.yml`:

```yaml
inventory-api:
  image: ghcr.io/cyberlightdev/inventory-voice-assistant:latest
  # build: ./inventory-api   ← remove or comment out
```

Then pull and start:

```bash
docker compose pull inventory-api
docker compose up -d
```

---

## Model selection

The LLM must support **OpenAI-compatible tool/function calling** via llama.cpp's server. Recommended models (quantized GGUF, Q4_K_M or better):

| Model | Notes |
|-------|-------|
| **Qwen3** (any size) | Excellent tool use; `--chat-template-kwargs '{"enable_thinking":false}'` is already set in compose to suppress thinking tokens |
| **Mistral 7B Instruct** | Reliable tool calls, lower VRAM |
| **Llama 3.1/3.2 Instruct** | Strong tool use at 8B |
| **Gemma 3** | Good option for tighter VRAM budgets |

> **Note:** If you use a non-Qwen3 model you may want to remove `--chat-template-kwargs` from the llama-cpp command in `docker-compose.yml`. That flag is Qwen3-specific and other models will ignore or mishandle it.

Download GGUF files from [Hugging Face](https://huggingface.co/models?library=gguf). Place in the repo root and set `LLAMA_CPP_MODEL=yourfile.gguf` in `.env`.

---

## Vision support

To enable the camera button (attach a photo to your next voice message):

1. Download the matching **mmproj** GGUF for your model (available alongside the base GGUF on Hugging Face — look for files with `mmproj` in the name)
2. Place it in the repo root
3. Set `MMPROJ_MODEL=mmproj-yourfile.gguf` in `.env`
4. Restart llama-cpp: `docker compose restart llama-cpp`

You can also configure the mmproj model through the settings UI (⚙ icon) after first boot. The camera button is automatically disabled when no mmproj model is configured.

---

## Conversation modes

### Hold-to-Talk
Press and hold the **Hold to Talk** button (or `Space`) to record. Release to submit.

### Conversation Mode
Click **Conv Mode** to enable continuous listening. The VAD (Voice Activity Detection) automatically detects speech and submits when you pause.

**Wake word** (optional): Set a wake word in settings (e.g. `hey box`). When set, the assistant ignores all audio until it hears the wake word. Once activated:
- A short ascending tone plays — the session is open
- You can issue commands freely for 30 seconds without repeating the wake word
- After 30 seconds of silence, a descending tone plays and the session closes

---

## Voice commands

The assistant understands natural language and maps it to these actions:

| What you say | What happens |
|---|---|
| "Set location to garage shelf three" | Creates or switches to that location |
| "Add a hammer" / "Found five zip ties" | Adds item(s) to current location |
| "Actually there are three, not five" | Updates quantity to absolute value |
| "Move the drill to the workshop" | Moves item to another location |
| "Where are my XLR cables?" | Searches all locations |
| "What locations do I have?" | Lists all locations |
| "Undo" / "That was wrong" / "Never mind" | Reverses the last action (up to 5 deep) |
| "Remove the broken shelf bracket" | Deletes an item entirely |

---

## Settings

All settings are accessible via the **⚙** icon in the top-right corner. Changes apply immediately — no container restart required — except:

- **LLM model (GGUF)**: requires `docker compose restart llama-cpp`
- **Vision projector (mmproj)**: requires `docker compose restart llama-cpp`

Settings are persisted to `./config/settings.json` (mounted into the container) and survive container restarts.

### Voice options

**Whisper models** (speech recognition):

| Model | VRAM | Notes |
|-------|------|-------|
| `tiny` | ~250 MB | Fastest, lowest accuracy |
| `base` | ~300 MB | |
| `small` | ~500 MB | Good balance (default) |
| `medium` | ~1.5 GB | |
| `large-v3` | ~3 GB | Best accuracy |

**Kokoro voices** (text-to-speech):

| Voice | Description |
|-------|-------------|
| `af_sky` | American female (default) |
| `af_bella` | American female |
| `am_adam` | American male |
| `am_michael` | American male |
| `bf_emma` | British female |
| `bm_george` | British male |

---

## Development

To build and run locally with live code changes:

```bash
# Build the inventory-api image from source
docker compose up --build inventory-api

# Or mount index.html for live UI edits without rebuilding:
# Add to docker-compose.yml volumes:
#   - ./inventory-api/index.html:/app/index.html
```

Project layout:

```
inventory-api/
  Dockerfile
  requirements.txt
  main.py           — FastAPI app, chat loop, config, audio proxies
  homebox_client.py — Sync Homebox REST API wrapper
  tools.py          — 9 tool functions + OpenAI JSON schemas
  index.html        — Single-page UI (served by FastAPI)
docker-compose.yml
.env.example
```

### Releasing

Push a semver tag to trigger the GHCR build:

```bash
git tag v1.0.0
git push origin v1.0.0
```

The workflow publishes `ghcr.io/cyberlightdev/inventory-voice-assistant:1.0.0`, `:1.0`, and `:latest`.

---

## Architecture notes

- **No external dependencies**: all inference (ASR, LLM, TTS) runs on local hardware
- **Session state** is in-memory: restarting `inventory-api` clears conversation history but not Homebox data
- **Config layering**: environment variables (from `.env` via docker-compose) set defaults on first boot; the settings UI writes `./config/settings.json` which overrides them on subsequent starts
- **Tool loop**: the chat endpoint runs up to 10 LLM→tool-call iterations per user message before giving up
- **History trim**: only the system prompt + last N turn-pairs are sent to the LLM (configurable, default 6 turns)

---

## License

MIT
