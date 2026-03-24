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
    china_summary = synthesize_with_deepseek(
        topic,
        [],  # no Baidu results, DeepSeek knowledge only
        deep=False,
    )

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

    print()
    info("You can now:")
    info("  • Press Enter to keep all")
    info("  • Type numbers to remove (e.g. '3,5')")
    info("  • Type 'major <number>' to upgrade a minor to major (e.g. 'major 5')")
    info("  • Type 'add' to add competitors manually")

    while True:
        action = ask("Keep all, remove numbers, or 'add'? [Enter=keep all]")

        if not action:
            break

        if action.lower().startswith("major "):
            parts = action.split()
            if len(parts) == 2 and parts[1].isdigit():
                idx = int(parts[1]) - 1
                if 0 <= idx < len(competitors):
                    competitors[idx]["tier"] = "major"
                    ok(f"Upgraded {competitors[idx]['name']} to major")

        elif action.lower() == "add":
            while True:
                name = ask("Competitor name (Enter to stop)")
                if not name:
                    break
                market = ask("Market? (global/india/china)") or "global"
                tier   = ask("Tier? (major/minor)") or "minor"
                notes  = ask("Notes? (optional)")
                competitors.append({"name": name, "market": market, "tier": tier, "notes": notes})
                ok(f"Added: {name} ({tier})")

        elif re.match(r'^[\d,\s]+$', action):
            to_remove = {int(x.strip()) - 1 for x in action.split(",") if x.strip().isdigit()}
            competitors = [c for i, c in enumerate(competitors) if i not in to_remove]
            info(f"Kept {len(competitors)} competitors.")
            # Re-print
            for i, c in enumerate(competitors, 1):
                print(f"  {i:>2}. [{c['market'].upper():<7}] {c['name']}")

        cont = ask("Done editing? [Enter=yes / 'add' to add more]")
        if not cont or cont.lower() != "add":
            break
        # loop back to add more

    ok(f"Final competitor list: {len(competitors)} competitors")
    return competitors


# ── Step 3: Gather links per competitor ───────────────────────────────────────

def _lookup_competitor(name: str) -> dict:
    """Auto-lookup Play Store ID and YouTube for one competitor. Runs in parallel."""
    result = {}

    # Play Store
    try:
        raw = gemini_search(
            f"What is the Google Play Store package ID for '{name}' app? "
            f"Return ONLY the package ID like 'ai.replika.app', nothing else."
        )
        pid = clean_play_store_id(raw.strip().split()[0] if raw else "")
        if pid:
            result["play_store_id"] = pid
    except Exception:
        pass

    # YouTube
    try:
        raw = gemini_search(
            f"What is the official YouTube channel handle for '{name}' app? "
            f"Return ONLY '@handle', nothing else."
        )
        handle = clean_youtube_handle(raw.strip().split()[0] if raw else "")
        if handle:
            result["youtube_channel"] = handle
    except Exception:
        pass

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
        if found.get("youtube_channel") and not comp.get("youtube_channel"):
            comp["youtube_channel"] = found["youtube_channel"]

    print(f"\n  ✅ Done.\n")

    # Show major competitors table
    info("⭐ MAJOR competitors (Play Store + Meta Ads + YouTube + web search):")
    print(f"\n  {'#':<4} {'Name':<22} {'Market':<8} {'Play Store ID':<30} {'YouTube':<20}")
    print(f"  {'─'*4} {'─'*22} {'─'*8} {'─'*30} {'─'*20}")
    for i, c in enumerate(competitors, 1):
        if c.get("tier") != "major":
            continue
        ps = c.get("play_store_id", "❓ not found")[:28]
        yt = c.get("youtube_channel", "")[:18]
        print(f"  {i:<4} {c['name']:<22} {c['market']:<8} {ps:<30} {yt:<20}")

    # Show minor competitors
    if minor:
        print()
        info("   MINOR competitors (web search only):")
        for i, c in enumerate(competitors, 1):
            if c.get("tier") == "major":
                continue
            print(f"  {i:<4} {c['name']:<22} {c['market']}")

    print()
    info("To fix any entry, type its number and the correct value.")
    info("Format: '3 com.correct.package' or '3 skip' to clear.")
    info("Press Enter when done.")
    print()

    while True:
        val = ask("Fix any? (e.g. '3 com.correct.package' or Enter to continue)")
        if not val:
            break
        parts = val.strip().split(None, 1)
        if len(parts) == 2 and parts[0].isdigit():
            idx = int(parts[0]) - 1
            if 0 <= idx < len(competitors):
                new_val = parts[1].strip()
                if new_val.lower() == "skip":
                    competitors[idx].pop("play_store_id", None)
                    info(f"Cleared Play Store ID for {competitors[idx]['name']}")
                else:
                    cleaned = clean_play_store_id(new_val)
                    if cleaned:
                        competitors[idx]["play_store_id"] = cleaned
                        info(f"Updated {competitors[idx]['name']} → {cleaned}")
                    else:
                        warn("Doesn't look like a valid package ID. Try again.")
        else:
            warn("Format: '<number> <package_id>'")

    # Meta Ads — show all at once, user pastes what they have
    h2("Meta Ads page IDs (optional)")
    info("For each competitor you want to scrape Meta ads, paste their Facebook Ads Library URL.")
    info("Format: '<number> <url_or_page_id>'  — or just press Enter to skip all.\n")

    for i, c in enumerate(competitors, 1):
        print(f"  {i}. {c['name']}")

    print()
    while True:
        val = ask("Add Meta Ads? (e.g. '1 https://facebook.com/ads/...pageid=123' or Enter to skip)")
        if not val:
            break
        parts = val.strip().split(None, 1)
        if len(parts) == 2 and parts[0].isdigit():
            idx = int(parts[0]) - 1
            if 0 <= idx < len(competitors):
                raw = parts[1].strip()
                id_match = re.search(r'view_all_page_id=(\d+)', raw)
                if id_match:
                    competitors[idx]["meta_ads_page_id"] = id_match.group(1)
                    competitors[idx]["meta_ads_url"]     = raw
                    ok(f"{competitors[idx]['name']} → page_id {id_match.group(1)}")
                elif re.match(r'^\d+$', raw):
                    competitors[idx]["meta_ads_page_id"] = raw
                    competitors[idx]["meta_ads_url"] = (
                        f"https://www.facebook.com/ads/library/?active_status=active&ad_type=all"
                        f"&country=IN&search_type=page&view_all_page_id={raw}"
                    )
                    ok(f"{competitors[idx]['name']} → page_id {raw}")
                else:
                    warn("Couldn't extract page ID. Paste the full Ads Library URL.")
        else:
            warn("Format: '<number> <url_or_id>'")

    # Skip competitors
    val = ask("Remove any competitors? (comma-separated numbers, or Enter to keep all)")
    if val and re.match(r'^[\d,\s]+$', val):
        to_remove = {int(x.strip()) - 1 for x in val.split(",") if x.strip().isdigit()}
        competitors = [c for i, c in enumerate(competitors) if i not in to_remove]
        ok(f"{len(competitors)} competitors remaining.")

    return competitors


# ── Step 4: Research parameters ───────────────────────────────────────────────

def step4_research_params(topic: str, competitors: list[dict]) -> dict:
    h2("Step 4 — Research parameters")

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

    # Show and confirm each parameter
    print()

    # Web search queries
    info("Web search queries:")
    for i, q in enumerate(params["web_search_queries"], 1):
        print(f"    {i}. {q}")
    val = ask("Add more web search queries? (comma-separated, or Enter to keep)")
    if val:
        params["web_search_queries"].extend([q.strip() for q in val.split(",") if q.strip()])

    # China search
    info("\nChina search queries:")
    for q in params["china_search_queries"]: print(f"    • {q}")
    val = ask("Modify? (Enter to keep)")
    if val:
        params["china_search_queries"] = [q.strip() for q in val.split(",") if q.strip()]

    # Reddit
    info("\nReddit queries:")
    for q in params["reddit_queries"]: print(f"    • {q}")
    info("Reddit subreddits:")
    for s in params["reddit_subreddits"]: print(f"    • r/{s}")
    val = ask("Add subreddits? (comma-separated, or Enter to keep)")
    if val:
        params["reddit_subreddits"].extend([s.strip() for s in val.split(",") if s.strip()])

    # Google Trends
    info(f"\nGoogle Trends keywords (suggested): {params['google_trends_keywords']}")
    info(f"Geo: {params['google_trends_geo']}")
    info("  Note: max 5 keywords total for Google Trends.")
    val = ask("Add more keywords? (comma-separated, or Enter to keep as-is)")
    if val:
        existing = [k.strip() for k in params["google_trends_keywords"].split(",") if k.strip()]
        new_keys = [k.strip() for k in val.split(",") if k.strip()]
        combined = existing + [k for k in new_keys if k not in existing]
        params["google_trends_keywords"] = ",".join(combined[:5])  # cap at 5
        info(f"  Final keywords: {params['google_trends_keywords']}")
    val = ask("Modify geo? (e.g. IN, US, or Enter to keep)")
    if val:
        params["google_trends_geo"] = val

    # YouTube
    info("\nYouTube search queries:")
    for q in params["youtube_search_queries"]: print(f"    • {q}")
    val = ask("Add more YouTube queries? (comma-separated, or Enter to keep)")
    if val:
        params["youtube_search_queries"].extend([q.strip() for q in val.split(",") if q.strip()])

    ok("Research parameters set.")
    return params


# ── Step 5: Write config + confirm ────────────────────────────────────────────

def step5_write_config(topic: str, competitors: list[dict], params: dict, summaries: dict) -> Path:
    h2("Step 5 — Config summary")

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
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2))
    ok(f"Config saved → {config_path}")
    return config_path


# ── Phase 1 orchestrator ───────────────────────────────────────────────────────

def phase1(topic: str) -> Path:
    h1(f"🔬 Research Agent — Phase 1: Briefing\n  Topic: {topic}")

    summaries   = step1_discover(topic)
    competitors = step2_confirm_competitors(topic, summaries)
    competitors = step3_gather_links(competitors)
    params      = step4_research_params(topic, competitors)
    config_path = step5_write_config(topic, competitors, params, summaries)

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
