"""FastAPI backend — serves UI and API for the voice inventory assistant."""

import json
import os
import uuid
from collections import deque
from pathlib import Path

import httpx
import requests
from fastapi import FastAPI, Header, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from homebox_client import HomeboxClient
from tools import TOOL_DEFINITIONS, TOOL_DISPATCH

# ------------------------------------------------------------------
# Config — env vars are defaults; /config/settings.json overrides them.
# No restart needed when settings change (except llama-cpp model).
# ------------------------------------------------------------------

CONFIG_FILE = Path("/config/settings.json")

# Internal service URLs — set by docker-compose, not user-configurable
LLAMA_CPP_URL = os.getenv("LLAMA_CPP_URL", "http://llama-cpp:8080")
WHISPER_URL   = os.getenv("WHISPER_URL",   "http://whisper:8000")
KOKORO_URL    = os.getenv("KOKORO_URL",    "http://kokoro:8880")


def _default_config() -> dict:
    """Build config from environment variables (the fallback layer)."""
    return {
        "homebox_url":    os.getenv("HOMEBOX_URL",    "http://homebox:7745"),
        "homebox_email":  os.getenv("HOMEBOX_EMAIL",  ""),
        "homebox_password": os.getenv("HOMEBOX_PASSWORD", ""),
        "llama_cpp_model": os.getenv("LLAMA_CPP_MODEL", "model.gguf"),
        "whisper_model":  os.getenv("WHISPER_MODEL",  "small"),
        "kokoro_voice":   os.getenv("KOKORO_VOICE",   "af_sky"),
        "history_turns":  int(os.getenv("HISTORY_TURNS", "6")),
    }


def load_config() -> dict:
    """Env vars → merged with config file overrides."""
    cfg = _default_config()
    if CONFIG_FILE.exists():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text()))
        except (json.JSONDecodeError, OSError):
            pass
    return cfg


# Live config dict — mutated in place by save_config so all endpoints
# immediately see the new values without a restart.
_cfg: dict = {}

# ------------------------------------------------------------------
# System prompt
# ------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a voice-operated inventory assistant. The user is physically sorting through bins and boxes and dictating items to you hands-free.

**Behavior:**
- Always call the appropriate tool immediately — never describe what you would do without doing it.
- After every tool call, read back exactly what changed in one natural sentence.
- Keep all responses short and speakable. No bullet points, no markdown, no lists.
- If no location is set and the user starts adding items, ask for the location before proceeding.

**Tool usage:**
- Use `set_location` at the start of each session or when the user moves to a new area. Strip filler words — "The Attic" becomes "Attic".
- Use `find_item` for ANY question about whether something exists or how many there are. NEVER use add_item to answer a question.
- Use `add_item` ONLY when the user explicitly states they physically found an item.
- Use `update_item_quantity` only for explicit corrections like "actually there are 5, not 3."
- Use `move_item` when the user wants to transfer items between locations. Source is always current location.
- Use `undo` when the user says "undo", "that's wrong", "go back", or "never mind."
- Use `remove_item` only when the user explicitly wants to delete an entry entirely.
- If set_location returns a "similar locations found" warning, tell the user and ask to confirm.

**Write protection (critical):**
- Write tools (add_item, update_item_quantity, remove_item, move_item) must ONLY be called when the user explicitly states they have physically found, moved, or want to delete an item.
- Never call a write tool in response to a question, lookup, or confirmation.
- Never confirm an action was taken unless a tool call returned a success response.
- If you cannot complete a request with available tools, say "I don't have a tool to do that yet."

**Normalization:**
- Expand abbreviations when context is clear — "xlr" → "XLR Cable", "uno" → "Arduino Uno".
- When uncertain, use best judgment and let the readback give the user a chance to correct.
"""

# ------------------------------------------------------------------
# App
# ------------------------------------------------------------------

app = FastAPI(title="Inventory API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------
# State
# ------------------------------------------------------------------

hb_client: HomeboxClient = None
sessions: dict[str, dict] = {}


@app.on_event("startup")
def startup():
    global hb_client, _cfg
    _cfg = load_config()
    hb_client = HomeboxClient(
        _cfg["homebox_url"], _cfg["homebox_email"], _cfg["homebox_password"]
    )


def get_or_create_session(session_id: str) -> dict:
    if session_id not in sessions:
        sessions[session_id] = {
            "current_location_id": None,
            "current_location_name": None,
            "undo_stack": deque(maxlen=5),
            "message_history": [{"role": "system", "content": SYSTEM_PROMPT}],
        }
    return sessions[session_id]


# ------------------------------------------------------------------
# Endpoints — UI and health
# ------------------------------------------------------------------

@app.get("/")
def serve_ui():
    return FileResponse("index.html")


@app.get("/health")
def health():
    return {"ok": True}


# ------------------------------------------------------------------
# Endpoints — Config
# ------------------------------------------------------------------

@app.get("/config")
def get_config():
    return {k: v for k, v in _cfg.items() if k != "homebox_password"}


class ConfigUpdate(BaseModel):
    homebox_url: str
    homebox_email: str
    homebox_password: str = ""  # blank = keep existing
    llama_cpp_model: str
    whisper_model: str
    kokoro_voice: str
    history_turns: int


@app.post("/config")
def save_config(data: ConfigUpdate):
    prev_model = _cfg.get("llama_cpp_model")

    # Build the update dict — omit blank password so we don't clobber it
    update = data.model_dump(exclude_none=True)
    if not update.get("homebox_password"):
        update.pop("homebox_password", None)
        update["homebox_password"] = _cfg.get("homebox_password", "")

    # Persist to config file
    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(update, indent=2))
    except OSError as e:
        return {"ok": False, "error": str(e)}

    # Apply immediately — no restart needed
    _cfg.update(update)
    _cfg["history_turns"] = int(_cfg["history_turns"])

    # Update Homebox client credentials live
    hb_client.update_credentials(
        _cfg["homebox_url"], _cfg["homebox_email"], _cfg["homebox_password"]
    )

    llama_restart_needed = _cfg["llama_cpp_model"] != prev_model
    return {"ok": True, "llama_restart_needed": llama_restart_needed}


@app.get("/models")
def list_models():
    p = Path("/models")
    models = sorted(f.name for f in p.glob("*.gguf")) if p.exists() else []
    return {"models": models}


# ------------------------------------------------------------------
# Endpoints — Audio proxies
# ------------------------------------------------------------------

@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    audio_bytes = await file.read()
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            f"{WHISPER_URL}/v1/audio/transcriptions",
            files={"file": (file.filename or "audio.webm", audio_bytes, file.content_type or "audio/webm")},
            data={"model": f"Systran/faster-whisper-{_cfg['whisper_model']}"},
        )
    r.raise_for_status()
    return {"text": r.json().get("text", "")}


class SpeakRequest(BaseModel):
    text: str


@app.post("/speak")
async def speak(req: SpeakRequest):
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            f"{KOKORO_URL}/v1/audio/speech",
            json={"model": "kokoro", "input": req.text, "voice": _cfg["kokoro_voice"]},
        )
    r.raise_for_status()
    return Response(content=r.content, media_type="audio/mpeg")


# ------------------------------------------------------------------
# Endpoints — Session
# ------------------------------------------------------------------

@app.get("/session/{session_id}")
def get_session(session_id: str):
    s = sessions.get(session_id)
    if not s:
        return {"current_location_name": None, "current_location_id": None, "undo_stack_length": 0}
    return {
        "current_location_name": s["current_location_name"],
        "current_location_id": s["current_location_id"],
        "undo_stack_length": len(s["undo_stack"]),
    }


@app.delete("/session/{session_id}")
def delete_session(session_id: str):
    sessions.pop(session_id, None)
    return {"ok": True}


# ------------------------------------------------------------------
# Endpoints — Chat
# ------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    image: str | None = None


@app.post("/chat")
def chat(req: ChatRequest, x_session_id: str = Header(default=None)):
    session_id = x_session_id or str(uuid.uuid4())
    session = get_or_create_session(session_id)
    history = session["message_history"]

    if req.image:
        user_content = [
            {"type": "text", "text": req.message},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{req.image}"}},
        ]
    else:
        user_content = req.message

    history.append({"role": "user", "content": user_content})

    # Trim: always keep system prompt (index 0) + last N turns
    history_turns = _cfg["history_turns"]
    max_len = 1 + history_turns * 2
    if len(history) > max_len:
        history[1:] = history[-(history_turns * 2):]

    for _ in range(10):
        response = requests.post(
            f"{LLAMA_CPP_URL}/v1/chat/completions",
            json={
                "model": _cfg["llama_cpp_model"],
                "messages": history,
                "tools": TOOL_DEFINITIONS,
                "tool_choice": "auto",
            },
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        message = data["choices"][0]["message"]
        history.append(message)

        tool_calls = message.get("tool_calls")
        if not tool_calls:
            return {"response": message.get("content", ""), "session_id": session_id}

        for call in tool_calls:
            fn_name = call["function"]["name"]
            try:
                fn_args = json.loads(call["function"]["arguments"])
            except (json.JSONDecodeError, KeyError):
                fn_args = {}

            tool_fn = TOOL_DISPATCH.get(fn_name)
            if tool_fn:
                try:
                    result = tool_fn(session, hb_client, **fn_args)
                except Exception as e:
                    result = f"Tool error: {e}"
            else:
                result = f"Unknown tool: {fn_name}"

            history.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "content": result,
            })

    return {"response": "I got stuck in a tool loop. Please try again.", "session_id": session_id}
