"""
Research Agent — Phase 1: Interactive Briefing
Guides you through collecting all research ingredients before scraping begins.

Usage:
    uv run python agent.py "companion apps"
    uv run python agent.py "kids homework help india"
"""
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Add tools/ to path so we can import them directly
sys.path.insert(0, str(Path(__file__).parent / "tools"))


# ── Terminal helpers ───────────────────────────────────────────────────────────

def h1(text):    print(f"\n{'═'*60}\n  {text}\n{'═'*60}")
def h2(text):    print(f"\n── {text} {'─'*(55-len(text))}")
def info(text):  print(f"  {text}")
def ask(prompt): return input(f"\n❓ {prompt} → ").strip()
def ok(text):    print(f"  ✅ {text}")
def warn(text):  print(f"  ⚠️  {text}")


# ── Data cleaners ──────────────────────────────────────────────────────────────

def clean_app_store_id(val: str) -> str:
    """Extract numeric App Store ID from any format."""
    val = val.strip()
    if not val or val.lower() in ("skip", "yes", "no"):
        return ""
    # Strip 'id' prefix (e.g. id1158555867 → 1158555867)
    if re.match(r'^id\d+$', val, re.IGNORECASE):
        return val[2:]
    # Full URL: extract numeric ID
    match = re.search(r'/id(\d+)', val)
    if match:
        return match.group(1)
    # Just numbers
    match = re.search(r'\b(\d{8,12})\b', val)
    if match:
        return match.group(1)
    # If it's not URL-like and has no dot, probably junk
    if val.startswith("http") or ("." not in val and not val.isdigit()):
        return ""
    return val


def clean_play_store_id(val: str) -> str:
    """Extract package ID from Play Store URLs or query strings."""
    val = val.strip()
    if not val or val.lower() in ("skip", "yes", "no"):
        return ""
    # Full URL
    if "play.google.com" in val:
        match = re.search(r'[?&]id=([^&\s]+)', val)
        return match.group(1) if match else ""
    # Query string: id=ai.replika.app&hl=en_IN
    if val.startswith("id="):
        val = val[3:]
    # Strip trailing query params
    val = val.split("&")[0].split("?")[0].strip()
    # Must look like a package ID (contains dots, no spaces)
    if "." in val and " " not in val and not val.startswith("http"):
        return val
    return ""


def clean_trustpilot_slug(val: str) -> str:
    """Extract slug from Trustpilot URL or return as-is."""
    val = val.strip()
    if not val or val.lower() in ("skip", "yes", "no"):
        return ""
    if "trustpilot.com/review/" in val:
        slug = val.split("trustpilot.com/review/")[-1]
        return slug.split("?")[0].split("/")[0].strip()
    # Remove protocol/www if someone pasted a domain
    if val.startswith("http"):
        return ""
    return val


def clean_youtube_handle(val: str) -> str:
    """Extract @handle from YouTube URL, or return as-is if already a handle."""
    val = val.strip()
    if not val or val.lower() in ("skip", "yes", "no"):
        return ""
    # Already a handle
    if val.startswith("@"):
        return val
    # YouTube URL with @handle
    match = re.search(r'youtube\.com/@([^/?&\s]+)', val)
    if match:
        return f"@{match.group(1)}"
    # YouTube channel URL
    match = re.search(r'youtube\.com/channel/([^/?&\s]+)', val)
    if match:
        return match.group(1)
    # Plain handle without @
    if re.match(r'^[A-Za-z0-9_.-]+$', val) and len(val) > 2:
        return f"@{val}"
    return ""


# ── LLM edit helper ────────────────────────────────────────────────────────────

def llm_edit(current, schema_hint: str, user_request: str):
    """Apply a natural-language edit to any JSON-serialisable state via Gemini.
    Returns the updated state, or the original on failure."""
    prompt = f"""You are updating a data structure based on a user request.

Current state:
{json.dumps(current, indent=2)}

What this structure represents: {schema_hint}

User request: "{user_request}"

Apply exactly what the user asked. Return ONLY valid JSON with the same top-level type (array or object). No markdown, no explanation."""
    raw = gemini(prompt)
    try:
        # Try array
        m = re.search(r'\[.*\]', raw, re.DOTALL)
        if m:
            return json.loads(m.group())
        # Try object
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception:
        pass
    warn("Couldn't parse LLM response — no changes made.")
    return current


# ── Gemini helper ──────────────────────────────────────────────────────────────

def gemini(prompt: str, json_mode: bool = False) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(temperature=0.2)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=config,
    )
    return response.text.strip()


def gemini_search(prompt: str) -> str:
    """Gemini with Google Search grounding."""
    api_key = os.environ.get("GEMINI_API_KEY")
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.2,
        ),
    )
    return response.text.strip()


# ── Step 1: Auto-discover market ───────────────────────────────────────────────

def step1_discover(topic: str) -> dict:
    h2("Step 1 — Auto-discovering market (this takes ~30s)")

    info(f"Searching global market for: {topic}...")
    global_summary = gemini_search(
        f"Research the global market for '{topic}'. Give me: market size, top 5-8 competitors (company names only, no descriptions), recent funding, and key trends. Be concise."
    )

    info("Searching India market...")
    india_summary = gemini_search(
        f"Research the '{topic}' market specifically in India. Give me: market size, top Indian + global players operating in India, growth trends, pricing norms. Be concise."
    )

    info("Searching China market...")
    from china_search import synthesize_with_deepseek
    china_summary = synthesize_with_deepseek(topic, [], deep=False)

    ok("Discovery complete.")
    return {
        "global": global_summary,
        "india":  india_summary,
        "china":  china_summary,
    }


# ── Step 2: Extract + confirm competitors ─────────────────────────────────────

def step2_confirm_competitors(topic: str, summaries: dict) -> list[dict]:
    h2("Step 2 — Competitors")

    info("Extracting competitors from research...")
    extraction_prompt = f"""
Based on these market research summaries for '{topic}', extract competitor companies/apps mentioned.

GLOBAL SUMMARY:
{summaries['global'][:2000]}

INDIA SUMMARY:
{summaries['india'][:2000]}

CHINA SUMMARY:
{summaries['china'][:1000]}

Classify each as "major" or "minor":
- major: well-known brand, significant user base (100K+ users), notable funding, or market leader
- minor: small startup, niche/regional player, limited presence, early stage

Return ONLY a JSON array (no markdown, no explanation):
[
  {{"name": "Replika", "market": "global", "tier": "major", "notes": "10M users, subscription model"}},
  {{"name": "YourDOST", "market": "india", "tier": "minor", "notes": "small Indian startup"}},
  {{"name": "Xiaoice", "market": "china", "tier": "major", "notes": "Microsoft spinoff, 660M users"}}
]
"""
    raw = gemini(extraction_prompt)
    # Parse JSON — extract array even if there's surrounding text
    try:
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        competitors = json.loads(match.group()) if match else []
    except Exception:
        competitors = []

    if not competitors:
        warn("Could not auto-extract competitors. Let's add them manually.")
        competitors = []

    # Print what was found — split by tier
    print()
    major = [c for c in competitors if c.get("tier") == "major"]
    minor = [c for c in competitors if c.get("tier") != "major"]

    if competitors:
        info(f"I found {len(competitors)} competitors ({len(major)} major, {len(minor)} minor):\n")
        info("  MAJOR — will scrape Play Store, Meta Ads, YouTube, web search:")
        for i, c in enumerate(competitors, 1):
            if c.get("tier") == "major":
                print(f"  {i:>2}. ⭐ [{c['market'].upper():<7}] {c['name']:<25} {c.get('notes','')[:50]}")
        print()
        info("  MINOR — will only do web search + website:")
        for i, c in enumerate(competitors, 1):
            if c.get("tier") != "major":
                print(f"  {i:>2}.    [{c['market'].upper():<7}] {c['name']:<25} {c.get('notes','')[:50]}")
    else:
        info("No competitors found automatically.")

    def _display_competitors(comps):
        major = [c for c in comps if c.get("tier") == "major"]
        minor = [c for c in comps if c.get("tier") != "major"]
        if major:
            print()
            info(f"  MAJOR ({len(major)}):")
            for i, c in enumerate(comps, 1):
                if c.get("tier") == "major":
                    print(f"  {i:>2}. ⭐ [{c['market'].upper():<7}] {c['name']:<25} {c.get('notes','')[:50]}")
        if minor:
            print()
            info(f"  MINOR ({len(minor)}):")
            for i, c in enumerate(comps, 1):
                if c.get("tier") != "major":
                    print(f"  {i:>2}.    [{c['market'].upper():<7}] {c['name']:<25} {c.get('notes','')[:50]}")

    schema = (
        "A list of competitor objects, each with: name (str), market ('global'|'india'|'china'), "
        "tier ('major'|'minor'), notes (str). Numbers in the user's request refer to the list position shown."
    )

    print()
    info("Tell me any changes in plain English — or press Enter to continue.")
    info("Examples: 'remove Kuki', 'make 9 and 12 major', 'add Chai AI as major global'")

    while True:
        action = ask("Any changes?")
        if not action:
            break
        competitors = llm_edit(competitors, schema, action)
        _display_competitors(competitors)

    ok(f"Final competitor list: {len(competitors)} competitors")
    return competitors


# ── Step 3: Gather links per competitor ───────────────────────────────────────

def _lookup_competitor(name: str) -> dict:
    """Auto-lookup Play Store, App Store, and YouTube for one competitor.
    All 3 sub-lookups run in parallel. The whole function runs in parallel per competitor."""
    from concurrent.futures import ThreadPoolExecutor

    def get_play_store():
        raw = gemini_search(
            f"What is the Google Play Store package ID for '{name}' app? "
            f"Return ONLY the package ID like 'ai.replika.app', nothing else."
        )
        return clean_play_store_id(raw.strip().split()[0] if raw else "")

    def get_app_store():
        raw = gemini_search(
            f"What is the Apple App Store numeric app ID for '{name}' app? "
            f"Return ONLY the numeric ID like '1158555867', nothing else."
        )
        return clean_app_store_id(raw.strip().split()[0] if raw else "")

    def get_youtube():
        raw = gemini_search(
            f"What is the official YouTube channel handle for '{name}' app? "
            f"Return ONLY '@handle', nothing else."
        )
        return clean_youtube_handle(raw.strip().split()[0] if raw else "")

    result = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        f_ps = ex.submit(get_play_store)
        f_as = ex.submit(get_app_store)
        f_yt = ex.submit(get_youtube)
        try:
            pid = f_ps.result()
            if pid: result["play_store_id"] = pid
        except Exception: pass
        try:
            aid = f_as.result()
            if aid: result["app_store_id"] = aid
        except Exception: pass
        try:
            handle = f_yt.result()
            if handle: result["youtube_channel"] = handle
        except Exception: pass

    return result


def step3_gather_links(competitors: list[dict]) -> list[dict]:
    h2("Step 3 — Gathering links")
    major = [c for c in competitors if c.get("tier") == "major"]
    minor = [c for c in competitors if c.get("tier") != "major"]
    info(f"Deep lookup for {len(major)} major competitors (Play Store + YouTube) in parallel...")
    info(f"Minor competitors ({len(minor)}) → web search only, no deep lookup.\n")

    from concurrent.futures import ThreadPoolExecutor, as_completed

    lookups = {}
    if major:
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(_lookup_competitor, c["name"]): c["name"] for c in major}
            done = 0
            for future in as_completed(futures):
                name = futures[future]
                done += 1
                print(f"  [{done:>2}/{len(major)}] {name[:40]}", end="\r", flush=True)
                try:
                    lookups[name] = future.result()
                except Exception:
                    lookups[name] = {}

    # Apply findings to major competitors only
    for comp in competitors:
        if comp.get("tier") != "major":
            continue
        found = lookups.get(comp["name"], {})
        if found.get("play_store_id") and not comp.get("play_store_id"):
            comp["play_store_id"] = found["play_store_id"]
        if found.get("app_store_id") and not comp.get("app_store_id"):
            comp["app_store_id"] = found["app_store_id"]
        if found.get("youtube_channel") and not comp.get("youtube_channel"):
            comp["youtube_channel"] = found["youtube_channel"]

    print(f"\n  ✅ Done.\n")

    # Show major competitors table
    info("⭐ MAJOR competitors (Play Store + App Store + Meta Ads + YouTube + web search):")
    print(f"\n  {'#':<4} {'Name':<22} {'Market':<8} {'Play Store ID':<28} {'App Store ID':<14} {'YouTube':<20}")
    print(f"  {'─'*4} {'─'*22} {'─'*8} {'─'*28} {'─'*14} {'─'*20}")
    for i, c in enumerate(competitors, 1):
        if c.get("tier") != "major":
            continue
        ps = c.get("play_store_id", "❓")[:26]
        ap = c.get("app_store_id",  "❓")[:12]
        yt = c.get("youtube_channel", "")[:18]
        print(f"  {i:<4} {c['name']:<22} {c['market']:<8} {ps:<28} {ap:<14} {yt:<20}")

    # Show minor competitors
    if minor:
        print()
        info("   MINOR competitors (web search only):")
        for i, c in enumerate(competitors, 1):
            if c.get("tier") == "major":
                continue
            print(f"  {i:<4} {c['name']:<22} {c['market']}")

    def _display_links(comps):
        print(f"\n  {'#':<4} {'Name':<22} {'Market':<8} {'Play Store ID':<28} {'App Store ID':<14} {'YouTube':<20}")
        print(f"  {'─'*4} {'─'*22} {'─'*8} {'─'*28} {'─'*14} {'─'*20}")
        for i, c in enumerate(comps, 1):
            if c.get("tier") != "major":
                continue
            ps = c.get("play_store_id", "❓")[:26]
            ap = c.get("app_store_id",  "❓")[:12]
            yt = c.get("youtube_channel", "")[:18]
            print(f"  {i:<4} {c['name']:<22} {c['market']:<8} {ps:<28} {ap:<14} {yt:<20}")

    schema = (
        "A list of competitor objects. Each major competitor may have: play_store_id (package like "
        "'ai.replika.app'), app_store_id (numeric string like '1158555867'), youtube_channel ('@handle'). "
        "Numbers refer to list position. Only update the fields the user mentions; leave everything else unchanged."
    )

    print()
    info("Tell me any corrections in plain English — or press Enter to continue.")
    info("Examples: 'Replika Play Store is ai.replika.app', 'clear YouTube for #3', 'set Chai App Store to 1544750895'")

    while True:
        val = ask("Any corrections?")
        if not val:
            break
        competitors = llm_edit(competitors, schema, val)
        _display_links(competitors)

    return competitors


# ── Step 4: Meta Ads page IDs ──────────────────────────────────────────────────

def _lookup_meta_page_id(name: str) -> str:
    """Try to find the Facebook Ads Library page ID for a competitor via Gemini."""
    try:
        raw = gemini_search(
            f"What is the official Facebook page ID for '{name}' app in the Facebook Ads Library? "
            f"Return ONLY the numeric page ID (e.g. '123456789012345'), nothing else."
        )
        match = re.search(r'\b(\d{10,20})\b', raw.strip() if raw else "")
        return match.group(1) if match else ""
    except Exception:
        return ""


def step4_meta_ads(competitors: list[dict]) -> list[dict]:
    h2("Step 4 — Meta Ads page IDs")

    major = [c for c in competitors if c.get("tier") == "major"]
    if not major:
        info("No major competitors — skipping.")
        return competitors

    info(f"Auto-looking up Facebook page IDs for {len(major)} major competitors...")

    from concurrent.futures import ThreadPoolExecutor, as_completed
    lookups = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(_lookup_meta_page_id, c["name"]): c["name"] for c in major}
        done = 0
        for future in as_completed(futures):
            name = futures[future]
            done += 1
            print(f"  [{done:>2}/{len(major)}] {name[:40]}", end="\r", flush=True)
            try:
                lookups[name] = future.result()
            except Exception:
                lookups[name] = ""

    # Apply findings
    for comp in competitors:
        if comp.get("tier") != "major":
            continue
        pid = lookups.get(comp["name"], "")
        if pid and not comp.get("meta_ads_page_id"):
            comp["meta_ads_page_id"] = pid
            comp["meta_ads_url"] = (
                f"https://www.facebook.com/ads/library/?active_status=active&ad_type=all"
                f"&country=IN&search_type=page&view_all_page_id={pid}"
            )

    print(f"\n  ✅ Done.\n")

    # Show table — major only
    print(f"  {'#':<4} {'Name':<25} {'Page ID':<20} {'Status'}")
    print(f"  {'─'*4} {'─'*25} {'─'*20} {'─'*10}")
    for i, c in enumerate(competitors, 1):
        if c.get("tier") != "major":
            continue
        pid    = c.get("meta_ads_page_id", "")
        status = "✅" if pid else "❓ missing"
        print(f"  {i:<4} {c['name']:<25} {pid:<20} {status}")

    def _display_meta(comps):
        print(f"\n  {'#':<4} {'Name':<25} {'Page ID':<22} {'Status'}")
        print(f"  {'─'*4} {'─'*25} {'─'*22} {'─'*10}")
        for i, c in enumerate(comps, 1):
            if c.get("tier") != "major":
                continue
            pid    = c.get("meta_ads_page_id", "")
            status = "✅" if pid else "❓ missing"
            print(f"  {i:<4} {c['name']:<25} {pid:<22} {status}")

    schema = (
        "A list of competitor objects. Each may have meta_ads_page_id (numeric string, e.g. '123456789012345') "
        "and meta_ads_url. The user may paste a full Facebook Ads Library URL — extract the page ID from "
        "'view_all_page_id=<id>' in the URL. Numbers refer to list position. Only update what the user mentions."
    )

    print()
    info("Tell me any page IDs in plain English — or press Enter to skip.")
    info("Examples: 'Replika is 12345678', 'set #3 to https://facebook.com/ads/...view_all_page_id=9876'")

    while True:
        val = ask("Any Meta Ads page IDs to add?")
        if not val:
            break
        competitors = llm_edit(competitors, schema, val)
        _display_meta(competitors)

    return competitors


# ── Step 5: Research parameters ───────────────────────────────────────────────

def step5_research_params(topic: str, competitors: list[dict]) -> dict:
    h2("Step 5 — Research parameters")


    comp_names = ", ".join(c["name"] for c in competitors[:6])
    info("Generating suggestions with Gemini...")

    suggestions_raw = gemini(f"""
For market research on '{topic}' with competitors: {comp_names}

Suggest research parameters. Return ONLY JSON (no markdown):
{{
  "web_search_queries": ["query 1", "query 2", "query 3"],
  "china_search_queries": ["query 1"],
  "reddit_queries": ["query 1", "query 2"],
  "reddit_subreddits": ["subreddit1", "subreddit2"],
  "google_trends_keywords": "keyword1,keyword2,keyword3",
  "google_trends_geo": "IN",
  "youtube_search_queries": ["query 1", "query 2"]
}}

Rules:
- web_search: mix of India-specific and global queries
- china_search: Chinese market focus
- reddit: specific pain point queries
- trends: up to 5 comma-separated keywords, compare the main competitors
- youtube: what someone would search to find reviews/content about this topic
""")

    try:
        match = re.search(r'\{.*\}', suggestions_raw, re.DOTALL)
        params = json.loads(match.group()) if match else {}
    except Exception:
        params = {}

    defaults = {
        "web_search_queries":   [f"{topic} market India 2025", f"{topic} global market 2025"],
        "china_search_queries": [f"{topic} China market 2025"],
        "reddit_queries":       [topic],
        "reddit_subreddits":    [],
        "google_trends_keywords": comp_names[:100],
        "google_trends_geo":    "IN",
        "youtube_search_queries": [f"{topic} app review"],
    }
    for k, v in defaults.items():
        if k not in params:
            params[k] = v

    # Show all params at once
    print()
    info("Web search queries:")
    for i, q in enumerate(params["web_search_queries"], 1):
        print(f"    {i}. {q}")

    info("\nChina search queries:")
    for q in params["china_search_queries"]: print(f"    • {q}")

    info("\nReddit:")
    for q in params["reddit_queries"]: print(f"    query  • {q}")
    for s in params["reddit_subreddits"]: print(f"    sub    • r/{s}")

    info(f"\nGoogle Trends: {params['google_trends_keywords']}  |  Geo: {params['google_trends_geo']}  (max 5 keywords)")

    info("\nYouTube search queries:")
    for q in params["youtube_search_queries"]: print(f"    • {q}")

    def _display_params(p):
        print()
        info("Web search queries:")
        for i, q in enumerate(p["web_search_queries"], 1): print(f"    {i}. {q}")
        info("\nChina search queries:")
        for q in p["china_search_queries"]: print(f"    • {q}")
        info("\nReddit:")
        for q in p["reddit_queries"]: print(f"    query  • {q}")
        for s in p["reddit_subreddits"]: print(f"    sub    • r/{s}")
        info(f"\nGoogle Trends: {p['google_trends_keywords']}  |  Geo: {p['google_trends_geo']}  (max 5 keywords)")
        info("\nYouTube search queries:")
        for q in p["youtube_search_queries"]: print(f"    • {q}")

    schema = (
        "A research params object with keys: web_search_queries (list), china_search_queries (list), "
        "reddit_queries (list), reddit_subreddits (list, no 'r/' prefix), google_trends_keywords "
        "(comma-separated string, max 5), google_trends_geo (2-letter country code), "
        "youtube_search_queries (list). Add/remove/change whatever the user asks."
    )

    print()
    info("Tell me any changes in plain English — or press Enter to accept all.")
    info("Examples: 'add r/replika to subreddits', 'remove web query 2', 'set geo to US'")

    while True:
        val = ask("Any changes?")
        if not val:
            break
        params = llm_edit(params, schema, val)
        _display_params(params)

    ok("Research parameters set.")
    return params


# ── Step 6: Write config + confirm ────────────────────────────────────────────

def step6_write_config(topic: str, competitors: list[dict], params: dict, summaries: dict) -> Path:
    h2("Step 6 — Config summary")

    slug = re.sub(r'[^a-z0-9]+', '-', topic.lower()).strip('-')
    research_dir = Path("research") / slug
    research_dir.mkdir(parents=True, exist_ok=True)
    (research_dir / "data").mkdir(exist_ok=True)

    config = {
        "topic":         topic,
        "slug":          slug,
        "created_at":    datetime.now().isoformat(),
        "markets":       ["global", "india", "china"],
        "competitors":   {
            "major": [c for c in competitors if c.get("tier") == "major"],
            "minor": [c for c in competitors if c.get("tier") != "major"],
        },
        "web_search":    {"queries": params["web_search_queries"]},
        "china_search":  {"queries": params["china_search_queries"]},
        "reddit":        {
            "queries":    params["reddit_queries"],
            "subreddits": params["reddit_subreddits"],
        },
        "google_trends": {
            "keywords": params["google_trends_keywords"],
            "geo":      params["google_trends_geo"],
        },
        "youtube": {
            "search_queries": params["youtube_search_queries"],
            "channels":       [c["youtube_channel"] for c in competitors
                               if clean_youtube_handle(c.get("youtube_channel", ""))],
        },
        "meta_ads": [
            {"name": c["name"], "page_id": c["meta_ads_page_id"], "url": c.get("meta_ads_url", "")}
            for c in competitors if c.get("tier") == "major" and c.get("meta_ads_page_id")
        ],
        "websites":      [{"name": c["name"], "url": c["website"]} for c in competitors if c.get("website")],
        "play_store":    [c["play_store_id"] for c in competitors
                          if c.get("tier") == "major" and clean_play_store_id(c.get("play_store_id", ""))],
        "app_store":     [c["app_store_id"] for c in competitors
                          if c.get("tier") == "major" and clean_app_store_id(c.get("app_store_id", ""))],
        "trustpilot":    [c["trustpilot_slug"] for c in competitors
                          if c.get("trustpilot_slug") and not c["trustpilot_slug"].startswith("http")],
        "discovery":     summaries,
    }

    # Summary printout
    print()
    info(f"Topic:             {topic}")
    info(f"Competitors:       {len(competitors)}")
    info(f"Play Store apps:   {len(config['play_store'])}")
    info(f"App Store apps:    {len(config['app_store'])}")
    info(f"Meta Ads pages:    {len(config['meta_ads'])}")
    info(f"Trustpilot slugs:  {len(config['trustpilot'])}")
    info(f"YouTube channels:  {len(config['youtube']['channels'])}")
    info(f"Web queries:       {len(config['web_search']['queries'])}")
    info(f"Reddit queries:    {len(config['reddit']['queries'])}")
    info(f"Trends keywords:   {config['google_trends']['keywords']}")
    info(f"\nOutput dir:        research/{slug}/")

    confirm = ask("\n▶ Save config and start Phase 2? [Enter=yes / 'no' to abort]")
    if confirm.lower() == "no":
        warn("Aborted. Config not saved.")
        sys.exit(0)

    config_path = research_dir / "config.json"

    # Archive existing config before overwriting
    if config_path.exists():
        try:
            old = json.loads(config_path.read_text())
            ts = old.get("created_at", "")[:19].replace(":", "-").replace("T", "_")
            archive = research_dir / f"config_{ts}.json"
            config_path.rename(archive)
            info(f"Archived old config → {archive.name}")
        except Exception:
            pass

    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2))
    ok(f"Config saved → {config_path}")
    return config_path


# ── Phase 1 orchestrator ───────────────────────────────────────────────────────

def phase1(topic: str) -> Path:
    h1(f"🔬 Research Agent — Phase 1: Briefing\n  Topic: {topic}")

    summaries   = step1_discover(topic)
    competitors = step2_confirm_competitors(topic, summaries)
    competitors = step3_gather_links(competitors)
    competitors = step4_meta_ads(competitors)
    params      = step5_research_params(topic, competitors)
    config_path = step6_write_config(topic, competitors, params, summaries)

    h1("✅ Phase 1 Complete")
    info(f"Config saved to: {config_path}")
    info("Run Phase 2 to start scraping:")
    info(f"  uv run python agent.py --run {config_path}")
    return config_path


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  uv run python agent.py 'companion apps'          # Phase 1: briefing")
        print("  uv run python agent.py --run research/slug/config.json  # Phase 2: execute")
        sys.exit(1)

    if sys.argv[1] == "--run":
        if len(sys.argv) < 3:
            print("❌ Provide config path: uv run python agent.py --run research/slug/config.json")
            sys.exit(1)
        print("Phase 2 coming soon...")
        # TODO: phase2(sys.argv[2])
    else:
        topic = " ".join(sys.argv[1:])
        phase1(topic)
