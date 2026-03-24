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
Based on these market research summaries for '{topic}', extract all competitor companies/apps mentioned.

GLOBAL SUMMARY:
{summaries['global'][:2000]}

INDIA SUMMARY:
{summaries['india'][:2000]}

CHINA SUMMARY:
{summaries['china'][:1000]}

Return ONLY a JSON array like this (no markdown, no explanation):
[
  {{"name": "Replika", "market": "global", "notes": "10M users, subscription model"}},
  {{"name": "YourDOST", "market": "india", "notes": "Indian mental wellness app"}},
  {{"name": "Xiaoice", "market": "china", "notes": "Microsoft spinoff, 660M users"}}
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

    # Print what was found
    print()
    if competitors:
        info(f"I found {len(competitors)} competitors:\n")
        for i, c in enumerate(competitors, 1):
            print(f"  {i:>2}. [{c['market'].upper():<7}] {c['name']:<25} {c.get('notes','')[:50]}")
    else:
        info("No competitors found automatically.")

    print()
    info("You can now:")
    info("  • Press Enter to keep all")
    info("  • Type numbers to remove (e.g. '3,5')")
    info("  • Type 'add' to add competitors manually")

    while True:
        action = ask("Keep all, remove numbers, or 'add'? [Enter=keep all]")

        if not action:
            break

        if action.lower() == "add":
            while True:
                name = ask("Competitor name (Enter to stop)")
                if not name:
                    break
                market = ask("Market? (global/india/china)") or "global"
                notes  = ask("Notes? (optional)")
                competitors.append({"name": name, "market": market, "notes": notes})
                ok(f"Added: {name}")

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

def step3_gather_links(competitors: list[dict]) -> list[dict]:
    h2("Step 3 — Gathering links for each competitor")
    info("I'll auto-search where I can. You only need to fill in what I can't find.\n")

    from app_store import search_apps

    for comp in competitors:
        name = comp["name"]
        print(f"\n  📦 {name} ({comp['market'].upper()})")
        print(f"  {'─'*40}")

        # --- App Store ---
        info("Searching App Store...")
        try:
            results = search_apps(name, country="us", limit=3)
            if results:
                best = results[0]
                print(f"     App Store found: {best['trackName']} (ID: {best['trackId']})")
                confirm = ask(f"Use App Store ID {best['trackId']} for {name}? [Enter=yes / type different ID / 'skip']")
                if not confirm:
                    comp["app_store_id"] = str(best["trackId"])
                elif confirm.lower() != "skip":
                    comp["app_store_id"] = confirm
            else:
                val = ask(f"App Store ID for {name}? ('skip' to skip)")
                if val.lower() != "skip":
                    comp["app_store_id"] = val
        except Exception:
            val = ask(f"App Store ID for {name}? ('skip' to skip)")
            if val and val.lower() != "skip":
                comp["app_store_id"] = val

        # --- Play Store ---
        info("Searching Play Store...")
        try:
            play_result = gemini_search(
                f"Find the Google Play Store package ID for the app '{name}'. "
                f"Return ONLY the package ID (e.g. ai.replika.app), nothing else."
            )
            play_id = play_result.strip().split()[0] if play_result else ""
            # Basic validation — package IDs have dots
            if "." in play_id and len(play_id) > 5:
                print(f"     Play Store found: {play_id}")
                confirm = ask(f"Use Play Store ID '{play_id}'? [Enter=yes / type different ID / 'skip']")
                if not confirm:
                    comp["play_store_id"] = play_id
                elif confirm.lower() != "skip":
                    comp["play_store_id"] = confirm
            else:
                val = ask(f"Play Store package ID for {name}? ('skip' to skip)")
                if val and val.lower() != "skip":
                    comp["play_store_id"] = val
        except Exception:
            val = ask(f"Play Store package ID for {name}? ('skip' to skip)")
            if val and val.lower() != "skip":
                comp["play_store_id"] = val

        # --- Meta Ads ---
        info("Meta Ads page ID — I can't find this automatically.")
        info(f"  Go to: https://www.facebook.com/{name.replace(' ', '')} → copy the page URL")
        val = ask(f"Meta Ads page URL or page ID for {name}? ('skip' to skip)")
        if val and val.lower() != "skip":
            # Extract page ID from URL if they pasted a full URL
            id_match = re.search(r'view_all_page_id=(\d+)', val)
            if id_match:
                comp["meta_ads_page_id"] = id_match.group(1)
                comp["meta_ads_url"]     = val
            elif val.isdigit():
                comp["meta_ads_page_id"] = val
                comp["meta_ads_url"]     = (
                    f"https://www.facebook.com/ads/library/?active_status=active&ad_type=all"
                    f"&country=IN&search_type=page&view_all_page_id={val}"
                )
            else:
                comp["meta_ads_url"] = val

        # --- Trustpilot ---
        slug_guess = name.lower().replace(" ", "")
        val = ask(f"Trustpilot slug for {name}? [Enter='{slug_guess}' / type different / 'skip']")
        if not val:
            comp["trustpilot_slug"] = slug_guess
        elif val.lower() != "skip":
            comp["trustpilot_slug"] = val

        # --- YouTube ---
        info("Searching YouTube channel...")
        try:
            yt_result = gemini_search(
                f"Find the official YouTube channel handle for '{name}' app/company. "
                f"Return ONLY the handle (e.g. @Replika), nothing else."
            )
            yt_handle = yt_result.strip().split()[0] if yt_result else ""
            if yt_handle.startswith("@"):
                print(f"     YouTube found: {yt_handle}")
                confirm = ask(f"Use YouTube channel '{yt_handle}'? [Enter=yes / type different / 'skip']")
                if not confirm:
                    comp["youtube_channel"] = yt_handle
                elif confirm.lower() != "skip":
                    comp["youtube_channel"] = confirm
            else:
                val = ask(f"YouTube channel handle for {name}? (e.g. @Replika / 'skip')")
                if val and val.lower() != "skip":
                    comp["youtube_channel"] = val
        except Exception:
            val = ask(f"YouTube channel handle for {name}? (e.g. @Replika / 'skip')")
            if val and val.lower() != "skip":
                comp["youtube_channel"] = val

        ok(f"{name} done.")

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
    info(f"\nGoogle Trends keywords: {params['google_trends_keywords']}")
    info(f"Geo: {params['google_trends_geo']}")
    val = ask("Modify keywords? (comma-separated, max 5, or Enter to keep)")
    if val:
        params["google_trends_keywords"] = val
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
        "competitors":   competitors,
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
            "channels":       [c["youtube_channel"] for c in competitors if c.get("youtube_channel")],
        },
        "meta_ads": [
            {"name": c["name"], "page_id": c["meta_ads_page_id"], "url": c.get("meta_ads_url", "")}
            for c in competitors if c.get("meta_ads_page_id")
        ],
        "play_store":    [c["play_store_id"] for c in competitors if c.get("play_store_id")],
        "app_store":     [c["app_store_id"] for c in competitors if c.get("app_store_id")],
        "trustpilot":    [c["trustpilot_slug"] for c in competitors if c.get("trustpilot_slug")],
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
