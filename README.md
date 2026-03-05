# homebox-ai-mcp

MCP server enabling LLM-driven inventory management via [Homebox](https://homebox.software).

## What This Is

A Python MCP (Model Context Protocol) server that acts as a bridge between an LLM and a Homebox instance. The LLM interacts with inventory through natural language, and this server translates tool calls into Homebox REST API requests.

## Quick Start

### Prerequisites

- A running Homebox instance
- Docker (recommended) or Python 3.12+

### Running with Docker Compose

The easiest way to run both Homebox and the MCP server together:

1. Copy the example environment file and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env`:

```env
HOMEBOX_EMAIL=you@example.com
HOMEBOX_PASSWORD=yourpassword
```

2. Start both services:

```bash
docker compose up -d
```

The MCP server will be available at `http://localhost:8100/mcp`.

### Adding to an Existing Homebox Install

If you already have Homebox running, you can run just the MCP server:

```bash
docker run -d \
  -e HOMEBOX_URL=http://your-homebox-host:7745 \
  -e HOMEBOX_EMAIL=you@example.com \
  -e HOMEBOX_PASSWORD=yourpassword \
  -p 8100:8100 \
  ghcr.io/yourusername/homebox-ai-mcp:latest
```

Or with Docker Compose, add this service to your existing `compose.yml`:

```yaml
services:
  homebox-mcp:
    image: ghcr.io/yourusername/homebox-ai-mcp:latest
    environment:
      HOMEBOX_URL: http://homebox:7745   # adjust to your Homebox host
      HOMEBOX_EMAIL: you@example.com
      HOMEBOX_PASSWORD: yourpassword
    ports:
      - "8100:8100"
```

### Connecting Your LLM Client

Point your MCP client at:

```
http://localhost:8100/mcp
```

This server uses the streamable HTTP transport, which is supported by Claude Desktop, Open WebUI, and any MCP-compatible client.

## Tools

| Tool | Description |
|------|-------------|
| `homebox_set_location` | Set a working location for subsequent operations (fuzzy match by name) |
| `homebox_get_session` | Show current working location and last operation |
| `homebox_search_locations` | Find locations by name |
| `homebox_create_location` | Create a new location, optionally nested under a parent |
| `homebox_search_items` | Search items by name, optionally scoped to a location |
| `homebox_add_item` | Add an item to a location with quantity, notes, and labels |
| `homebox_update_item` | Update an item's name, quantity, notes, or location |
| `homebox_undo_last` | Undo the most recent create or update operation |

## Architecture

```
LLM (Claude / Open WebUI / custom app)
    ↓ MCP protocol (streamable HTTP, port 8100)
homebox-ai-mcp (this project)
    ↓ REST API (HTTP)
Homebox (Go app, port 7745)
```

- **Session state** — tracks "current location" and "last operation" per conversation for natural follow-up commands
- **Fuzzy matching** — location names are matched case-insensitively with fuzzy fallback, so "store room" finds "Storeroom"
- **Undo support** — every mutating tool snapshots the previous state; `homebox_undo_last` replays the inverse

## Configuration

All configuration is via environment variables (or a `.env` file):

| Variable | Default | Description |
|----------|---------|-------------|
| `HOMEBOX_URL` | `http://localhost:7745` | URL of your Homebox instance |
| `HOMEBOX_EMAIL` | *(required)* | Homebox account email |
| `HOMEBOX_PASSWORD` | *(required)* | Homebox account password |
| `MCP_PORT` | `8100` | Port for the MCP server |
| `SESSION_FILE` | `/data/sessions.json` | Path for session persistence |

## Persisting Session State

By default, session state (current working location and undo history) is stored in-memory and lost when the container restarts. This is fine for most use cases.

If you want session state to survive restarts, mount a volume for the session file:

```bash
docker run -d \
  -e HOMEBOX_URL=http://your-homebox-host:7745 \
  -e HOMEBOX_EMAIL=you@example.com \
  -e HOMEBOX_PASSWORD=yourpassword \
  -v homebox-mcp-data:/data \
  -p 8100:8100 \
  ghcr.io/yourusername/homebox-ai-mcp:latest
```

Or in Docker Compose:

```yaml
services:
  homebox-mcp:
    image: ghcr.io/yourusername/homebox-ai-mcp:latest
    environment:
      HOMEBOX_URL: http://homebox:7745
      HOMEBOX_EMAIL: you@example.com
      HOMEBOX_PASSWORD: yourpassword
    ports:
      - "8100:8100"
    volumes:
      - homebox-mcp-data:/data

volumes:
  homebox-mcp-data:
```

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest

# Run server locally (requires .env or env vars set)
python -m homebox_mcp.server

# Build and run with Docker
docker compose up --build
```
