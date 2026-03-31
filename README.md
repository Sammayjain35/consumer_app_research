# Research Agent v2

A three-phase market research system that pulls real data from 9 sources — Reddit, YouTube, Google Play Store, iOS App Store, Google Trends, Meta Ads Library, web search, Trustpilot, and Baidu/Chinese search — and synthesizes it into a structured analyst-grade report using Gemini.

Built to answer questions like: *"What does the astrology app market in India actually look like?"* or *"Who are the real competitors in AI companion apps, and what do users actually complain about?"*

---

## What It Does

Most market research is slow, expensive, or generic. This tool runs parallel scrapes across every relevant data source, then has an LLM synthesize everything into a single coherent report — with real user quotes, competitor breakdowns, ad strategy analysis, and trend data.

**Example reports from this repo:**
- `research/astrology-india/` — Covers AstroTalk ($77M revenue, IPO-bound), Astroyogi, InstaAstro, VAMA, and 5 others. Includes Play Store review analysis, Google Trends, Meta ad creative breakdown, Reddit sentiment, and China market comparison ($14B mysticism market). Identifies AstroTalk as a 7.7x revenue monopoly over #2.
- `research/companion-apps/` — Global + India + China market sizing, Character.AI vs Replika vs Wysa competitor landscape, Play Store review sentiment across 10 apps, Meta ad strategy analysis, Reddit UX complaints, and monetization failure patterns.

---

## Three Phases

### Phase 1 — Config Builder (interactive, in Claude Code chat)

You describe a market. Claude identifies competitors, looks up their app IDs, Play Store package names, Facebook Page IDs, Reddit communities, and search queries — and outputs a `config.json` with everything scoped for Phase 2.

No scripting. No manual lookup. You describe what you want to research; Claude builds the research plan.

Output: `research/<slug>/config.json`

### Phase 2 — Data Extraction (parallel, automated)

Reads the config and runs all tools in parallel:

```bash
uv run python phase2.py research/<slug>/config.json
```

Typically takes 5–15 minutes depending on scope. Data lands in `research/<slug>/data/`.

| Source | What it collects |
|--------|-----------------|
| `web_search` | Market size articles, funding news, business model coverage |
| `china_search` | Baidu search + DeepSeek for Chinese market context |
| `play_store` | Reviews, ratings, and recent complaints for each competitor app |
| `app_store` | iOS reviews and app metadata |
| `youtube` | Channel stats, top videos, search results |
| `reddit` | Posts across relevant subreddits with sentiment |
| `google_trends` | Interest over time, regional breakdown, related queries |
| `meta_ads` | Active ad creatives from Facebook Ads Library + Gemini video analysis |
| `trustpilot` | Third-party reviews for web-first competitors |

### Phase 3 — Synthesis (Gemini writes the report)

Reads all collected data, calls Gemini in multiple structured passes, and writes `research/<slug>/report.md`:

```bash
uv run python phase3.py research/<slug>/config.json
```

The report covers:
- **Executive summary** with key numbers
- **Market sizing** — global, India, China with CAGR projections
- **Competitor landscape** — positioning, revenue, user signals, ad strategy
- **User sentiment** — what real users praise and complain about (sourced from reviews + Reddit)
- **Ad creative analysis** — what messaging competitors are running in paid channels
- **Strategic gaps** — where the market is underserved

---

## MCP Server — Use as a Live Tool in Claude

Beyond the 3-phase pipeline, the research tools are also exposed as an MCP server — so any Claude session (or any MCP-compatible AI) can call them live.

The server is publicly hosted. Add it to Claude Code by creating `~/.claude/mcp.json`:

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

Restart Claude Code. Then in any session:
- *"Search Reddit for opinions on Zepto vs Blinkit"*
- *"Get Google Trends for AstroTalk, Astroyogi, InstaAstro in India"*
- *"Fetch Play Store reviews for com.astrotalk"*
- *"What are people saying about AI companion apps on YouTube?"*

Claude calls the tools automatically and returns real data.

### Available MCP Tools

| Tool | Description |
|------|-------------|
| `reddit_search` | Search Reddit posts by query, optionally scoped to subreddits |
| `youtube_search` | Search YouTube videos by keyword |
| `youtube_channel` | Get channel stats + top videos by handle |
| `play_store_reviews` | Fetch Google Play Store reviews by package ID |
| `app_store_reviews` | Fetch iOS App Store reviews by iTunes app ID |
| `app_store_search` | Search the App Store by keyword to find app IDs |
| `google_trends` | Interest over time, regional breakdown, related queries for up to 5 keywords |

---

## Setup

```bash
git clone <this-repo>
cd research_v2
cp .env.example .env
# Fill in API keys
uv sync
```

### API Keys

| Key | Used by | Where to get |
|-----|---------|-------------|
| `GEMINI_API_KEY` | Phase 3 synthesis + Meta ad video analysis | [aistudio.google.com](https://aistudio.google.com) |
| `YOUTUBE_API_KEY` | youtube.py | [Google Cloud Console](https://console.cloud.google.com) → YouTube Data API v3 |
| `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` | reddit.py | [reddit.com/prefs/apps](https://reddit.com/prefs/apps) → create script app |

No API key needed: `play_store`, `app_store`, `google_trends`, `trustpilot`, `web_search`

---

## Running Tools Standalone

Every tool in `tools/` is independently runnable:

```bash
uv run python tools/reddit.py --search "astrology app india" --subreddits india --max 50
uv run python tools/youtube.py --channel "@AstroTalk" --search "astrology app review"
uv run python tools/play_store.py com.astrotalk --max 200
uv run python tools/app_store.py --app-id 1208433822 --max 100
uv run python tools/google_trends.py --keywords "AstroTalk,Astroyogi,InstaAstro" --geo IN
uv run python tools/web_search.py --query "astrology app India market size 2024" --extract
uv run python tools/meta_ads.py --page-id 1497921286936951 --name AstroTalk
uv run python tools/trustpilot.py --company astrotalk
```

---

## Running the MCP Server Locally

```bash
uv run python mcp_server.py
# Starts on http://localhost:8000/mcp
```

Point `~/.claude/mcp.json` to `http://localhost:8000/mcp` to use the local version.

---

## Deploy Your Own MCP Server on Railway

```bash
railway login
railway init
railway up --detach
railway domain
railway variables set \
  YOUTUBE_API_KEY=your_key \
  REDDIT_CLIENT_ID=your_id \
  REDDIT_CLIENT_SECRET=your_secret \
  GEMINI_API_KEY=your_key
```

Then update `~/.claude/mcp.json` with your Railway domain.

---

## Project Structure

```
research_v2/
├── phase2.py             Parallel data extraction
├── phase3.py             Gemini synthesis → report.md
├── mcp_server.py         MCP server (HTTP, Railway-hosted)
├── PHASE1.md             Phase 1 instructions for Claude Code sessions
├── tools/                All research tools (standalone + called by phase2)
├── research/             Per-topic output
│   └── <slug>/
│       ├── config.json   Phase 1 output
│       ├── report.md     Phase 3 output
│       └── data/         Phase 2 output (all sources)
├── Dockerfile
└── .env.example
```
