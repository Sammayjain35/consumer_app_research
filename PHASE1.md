# Phase 1 — Research Config Builder

Phase 1 is done interactively in a Claude Code session (this chat).
I research the topic, present findings, and we build `config.json` together.
Output → `research/<slug>/config.json`

---

## Steps I follow every time

### Step 1 — Topic & markets
- Confirm the exact topic string and slug
- Confirm markets: default is `["global", "india", "china"]`

### Step 2 — Market discovery
- Search global market: size, key players, trends, recent funding
- Search India market: size, Indian + global players, pricing norms
- Search China market: key players, regulations, trends
- Present a summary of each

### Step 3 — Competitors
Present a numbered list. For each competitor I collect:

| Field | Description |
|-------|-------------|
| `name` | Full brand/app name |
| `market` | `global` / `india` / `china` |
| `tier` | `major` (deep scraping) or `minor` (web search only) |
| `notes` | Key facts (users, funding, positioning) |
| `website` | Homepage URL |

**Major competitors** also need:
| Field | Description |
|-------|-------------|
| `play_store_id` | e.g. `ai.replika.app` |
| `app_store_id` | Numeric ID e.g. `1158555867` |
| `youtube_channel` | e.g. `@Replika` |
| `meta_ads_page_id` | Facebook Ads Library numeric page ID |
| `trustpilot_slug` | e.g. `replika` (optional) |

**Tier rule:**
- `major` = well-known brand, 100K+ users, notable funding, or market leader
- `minor` = small startup, niche/regional, early stage

### Step 4 — Research parameters

| Field | Description |
|-------|-------------|
| `web_search_queries` | 8–12 queries mixing India-specific + global |
| `china_search_queries` | 3–5 queries for Chinese market |
| `reddit_queries` | 3–5 pain point / sentiment queries |
| `reddit_subreddits` | 3–5 relevant subreddits (no `r/` prefix) |
| `google_trends_keywords` | Up to 5 comma-separated keywords (competitor names) |
| `google_trends_geo` | 2-letter code, default `IN` |
| `youtube_search_queries` | 3–5 queries for reviews / comparisons |

### Step 5 — Write config
Write `research/<slug>/config.json`. Archive any existing config with a timestamp.

---

## Config JSON structure

```json
{
  "topic": "companion apps",
  "slug": "companion-apps",
  "created_at": "<ISO timestamp>",
  "markets": ["global", "india", "china"],

  "competitors": {
    "major": [
      {
        "name": "Replika",
        "market": "global",
        "tier": "major",
        "notes": "10M users, subscription model",
        "website": "https://replika.com",
        "play_store_id": "ai.replika.app",
        "app_store_id": "1158555867",
        "youtube_channel": "@Replika",
        "meta_ads_page_id": "123456789",
        "trustpilot_slug": "replika"
      }
    ],
    "minor": [
      {
        "name": "Rumik AI",
        "market": "india",
        "tier": "minor",
        "notes": "Indian startup",
        "website": "https://rumik.ai"
      }
    ]
  },

  "web_search":   { "queries": ["..."] },
  "china_search": { "queries": ["..."] },
  "reddit":       { "queries": ["..."], "subreddits": ["..."] },
  "google_trends": { "keywords": "Replika,Character AI", "geo": "IN" },
  "youtube":      { "search_queries": ["..."], "channels": ["@Replika"] },

  "meta_ads": [
    { "name": "Replika", "page_id": "123456789", "url": "https://facebook.com/ads/library/..." }
  ],
  "websites":   [{ "name": "Replika", "url": "https://replika.com" }],
  "play_store": ["ai.replika.app"],
  "app_store":  ["1158555867"],
  "trustpilot": ["replika"],

  "discovery": {
    "global": "<market summary>",
    "india":  "<market summary>",
    "china":  "<market summary>"
  }
}
```

---

## Rules

- Never skip a step — always complete all 5 before writing the config
- Always confirm competitors with the user before moving to Step 4
- `google_trends_keywords` hard cap: 5 keywords
- `meta_ads_page_id` is optional — mark as missing, user can add later
- Archive old config before overwriting (rename to `config_<timestamp>.json`)
