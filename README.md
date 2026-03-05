# homebox-ai-mcp

MCP server enabling LLM-driven inventory management via [Homebox](https://homebox.software).

## What This Is

A Python MCP (Model Context Protocol) server that acts as a bridge between an LLM and a Homebox instance. The LLM interacts with inventory through natural language, and this server translates tool calls into Homebox REST API requests.

## Architecture

```
LLM (Open WebUI / custom app / Claude)
    ↓ MCP protocol (streamable HTTP, port 8100)
homebox-ai-mcp (this project)
    ↓ REST API (HTTP, internal Docker network)
Homebox (Go app, port 7745)
```

## Key Design Decisions

- **Thin adapter** — business logic lives in Homebox; this server handles session state, tool mapping, and response formatting
- **Session state** — tracks "current location" and "last operation" for conversational context (web UI users don't need this)
- **Search-before-add pattern** — deduplication is an LLM behavior (via system prompt), not a tool-level enforcement
- **Undo via operation log** — every mutating tool snapshots the previous entity state; undo replays the inverse

## Development

### Prerequisites

- Python 3.12+
- A running Homebox instance (use `docker-compose up homebox` to start one)

### Setup

```bash
pip install -e ".[dev]"
```

### Run

```bash
# Needs HOMEBOX_URL, HOMEBOX_EMAIL, HOMEBOX_PASSWORD env vars
python -m homebox_mcp.server
```

### Test

```bash
pytest
```

### Docker

```bash
docker compose up --build
```

