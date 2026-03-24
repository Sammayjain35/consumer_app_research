# Research v2

## What This Is

Business research project — tools-first setup for comprehensive market research.
Parallel to `research/` (v1). Focus: better tools, reusable across any research topic.

**No centralized scoring. No forced verdicts. Objective = comprehensive research.**

---

## Python Environment

- **ALWAYS** use `uv run python tools/<tool>.py` — never `python` or `python3`
- **ALWAYS** use `uv add package` — never `pip install`

---

## Tools

All tools live in `tools/`. Each is standalone — runnable from the project root.

| Tool | Command | Purpose |
|------|---------|---------|
| `meta_ads.py` | `uv run python tools/meta_ads.py --page-id <id> --name <brand>` | Scrape Facebook Ads Library + Gemini video analysis |
| `play_store.py` | `uv run python tools/play_store.py <package_id> --max 500` | Google Play Store reviews + app metadata |
| `app_store.py` | `uv run python tools/app_store.py --app-id <id> --max 200` | iOS App Store reviews + search |
| `youtube.py` | `uv run python tools/youtube.py --channel "@handle"` | YouTube channel stats, top videos, search |
| `reddit.py` | `uv run python tools/reddit.py --search "query" --subreddits india` | Reddit post search + sentiment |
| `web_search.py` | `uv run python tools/web_search.py --query "..." --extract` | DuckDuckGo search + article extraction |
| `google_trends.py` | `uv run python tools/google_trends.py --keywords "a,b,c" --geo IN` | Google Trends — interest over time + regional |
| `trustpilot.py` | `uv run python tools/trustpilot.py --company <slug>` | Trustpilot competitor reviews |

### API Keys Required

Copy `.env.example` to `.env` and fill in:

```bash
cp .env.example .env
```

| Key | Tool | Where to get |
|-----|------|-------------|
| `GEMINI_API_KEY` | meta_ads.py | aistudio.google.com |
| `YOUTUBE_API_KEY` | youtube.py | console.cloud.google.com → YouTube Data API v3 |
| `REDDIT_CLIENT_ID/SECRET` | reddit.py | reddit.com/prefs/apps → create script app |

Tools without API keys (no setup needed): `play_store.py`, `app_store.py`, `web_search.py`, `google_trends.py`, `trustpilot.py`

---

## Data Output

All tool output goes to `data/<tool_name>/<target>/`:

```
data/
├── meta_ads/BrandName/       ad_001.mp4, ad_001.json (with Gemini analysis)
├── play_store/com.example/   reviews.json, reviews.csv
├── app_store/1234567890/     reviews.json, reviews.csv
├── youtube/ChannelName.json
├── reddit/search_query/      posts.json, posts.csv
├── web_search/query/         results.json, summary.txt
├── google_trends/            keywords.json
└── trustpilot/company/       reviews.json, reviews.csv
```

---

## Meta Ads Config Format

For scraping multiple brands at once:

```json
{
  "config": {
    "default_max_ads_per_competitor": 15,
    "output_directory": "data/meta_ads"
  },
  "competitors": [
    {
      "name": "BrandName",
      "page_id": "123456789",
      "category": "category_tag",
      "url": "https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=ALL&is_targeted_country=false&media_type=all&search_type=page&sort_data[direction]=desc&sort_data[mode]=total_impressions&view_all_page_id=123456789"
    }
  ]
}
```

---

## 3-Phase Agent

| Phase | How | Script |
|-------|-----|--------|
| **Phase 1** — Config building | Interactive in Claude Code chat. Follow `PHASE1.md`. | None — outputs `config.json` |
| **Phase 2** — Data extraction | Reads config, runs all tools in parallel | `uv run python phase2.py research/<slug>/config.json` |
| **Phase 3** — Synthesis | Reads all data, Gemini writes `report.md` | `uv run python phase3.py research/<slug>/config.json` |

### Research folder structure

```
research/
└── <slug>/
    ├── config.json          ← Phase 1 output
    ├── config_<ts>.json     ← archived old configs
    ├── report.md            ← Phase 3 output
    └── data/                ← Phase 2 output
        ├── web_search/
        ├── china_search/
        ├── play_store/
        ├── app_store/
        ├── reddit/
        ├── youtube/
        ├── google_trends/
        ├── meta_ads/
        └── trustpilot/
```

---

## Project Structure

```
research_v2/
├── CLAUDE.md
├── PHASE1.md           (Phase 1 template — follow this in every chat session)
├── phase2.py           (data extraction)
├── phase3.py           (synthesis + report)
├── pyproject.toml
├── .python-version     (3.12)
├── .env                (secrets — not in git)
├── .env.example        (template)
├── tools/              (all research tools)
├── research/           (per-topic output: config + data + report)
└── agent.py            (old Phase 1 terminal script — deprecated)
```
