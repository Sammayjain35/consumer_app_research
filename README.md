# Research Agent v2

A market research toolkit that scrapes real data from Reddit, YouTube, Google Play Store, iOS App Store, and Google Trends — exposed as an MCP (Model Context Protocol) server so Claude can use it as a live research tool.

---

## MCP Server — Connect to Claude

The server is live and publicly accessible. Add it to Claude Code by creating `~/.claude/mcp.json`:

```json
{
  "mcpServers": {
    "research": {
      "type": "http",
      "url": "https://grand-elegance-production-eb9c.up.railway.app/mcp"
    }
  }
}
```

Restart Claude Code. Then in any session you can ask:
- *"Search Reddit for opinions on Zepto vs Blinkit"*
- *"Get Google Trends for Zepto, Blinkit, Swiggy Instamart in India"*
- *"Fetch Play Store reviews for com.zepto.app"*
- *"What are people saying about quick commerce on YouTube?"*

Claude will call the tools automatically and return real data.

---

## Available MCP Tools

| Tool | Description |
|------|-------------|
| `reddit_search` | Search Reddit posts by query, optionally scoped to specific subreddits |
| `youtube_search` | Search YouTube videos by keyword, sorted by views or relevance |
| `youtube_channel` | Get channel stats + top videos by handle (e.g. `@Zepto`) |
| `play_store_reviews` | Fetch Google Play Store reviews by package ID |
| `app_store_reviews` | Fetch iOS App Store reviews by iTunes app ID |
| `app_store_search` | Search the App Store by keyword to discover app IDs |
| `google_trends` | Interest over time, regional breakdown, and related queries for up to 5 keywords |

---

## Project Structure

```
research_v2/
├── mcp_server.py         MCP server — exposes all tools over HTTP
├── Dockerfile            For Railway deployment
├── .dockerignore
├── tools/
│   ├── reddit.py
│   ├── youtube.py
│   ├── play_store.py
│   ├── app_store.py
│   ├── google_trends.py
│   ├── trustpilot.py     (not in MCP — uses Playwright)
│   ├── web_search.py     (not in MCP — excluded by choice)
│   └── meta_ads*.py      (not in MCP — uses Playwright)
├── phase2.py             Batch data extraction from config.json
├── phase3.py             Report synthesis via Gemini
├── CLAUDE.md             Project instructions for Claude Code sessions
└── PHASE1.md             Research config builder template
```

---

## Running Tools Locally

```bash
# Always use uv
uv run python tools/reddit.py --search "quick commerce india" --max 50
uv run python tools/youtube.py --search "Zepto review" --max 20
uv run python tools/play_store.py com.zepto.app --max 200
uv run python tools/app_store.py --app-id 1642910906 --max 100
uv run python tools/google_trends.py --keywords "Zepto,Blinkit" --geo IN
```

---

## Running the MCP Server Locally

```bash
uv run python mcp_server.py
# Starts on http://localhost:8000/mcp
```

To use the local version in Claude, point `~/.claude/mcp.json` to `http://localhost:8000/mcp` instead.

---

## Deploying Your Own Instance on Railway

### 1. Prerequisites

- [Railway account](https://railway.com)
- Railway CLI: `npm install -g @railway/cli`
- API keys (see below)

### 2. Clone and deploy

```bash
git clone <this-repo>
cd research_v2
railway login
railway init
railway up --detach
railway domain
```

### 3. Set environment variables on Railway

```bash
railway variables set \
  YOUTUBE_API_KEY=your_key \
  REDDIT_CLIENT_ID=your_id \
  REDDIT_CLIENT_SECRET=your_secret \
  GEMINI_API_KEY=your_key
```

### 4. Update your mcp.json with the new Railway URL

---

## API Keys

| Key | Tool | Where to get |
|-----|------|-------------|
| `YOUTUBE_API_KEY` | youtube tools | [Google Cloud Console](https://console.cloud.google.com) → YouTube Data API v3 |
| `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` | reddit tool | [reddit.com/prefs/apps](https://reddit.com/prefs/apps) → create script app |
| `GEMINI_API_KEY` | phase3 synthesis | [Google AI Studio](https://aistudio.google.com) |

Tools that need no API key: `play_store`, `app_store`, `google_trends`

---

## 3-Phase Research Agent (Local)

Beyond the MCP server, the project has a 3-phase pipeline for full research reports:

| Phase | How | Command |
|-------|-----|---------|
| **Phase 1** — Config building | Interactive in Claude Code chat (follow `PHASE1.md`) | None — outputs `research/<slug>/config.json` |
| **Phase 2** — Data extraction | Runs all tools in parallel from config | `uv run python phase2.py research/<slug>/config.json` |
| **Phase 3** — Synthesis | Gemini reads all data and writes a report | `uv run python phase3.py research/<slug>/config.json` |

---

## Setup

```bash
cp .env.example .env
# Fill in API keys in .env
uv sync
```
