"""
Phase 3 — Synthesis & Report
Reads all collected data from research/<slug>/data/ and synthesizes
a full market research report using Gemini.

Usage:
    uv run python phase3.py research/companion-apps/config.json
"""
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


# ── Data loader ────────────────────────────────────────────────────────────────

def load_data(data_dir: Path) -> dict:
    """Load all collected data from the data directory into a dict."""
    data = {}

    def read_json(path: Path):
        try:
            return json.loads(path.read_text())
        except Exception:
            return None

    # Web search summaries
    web_dir = data_dir / "web_search"
    if web_dir.exists():
        data["web_search"] = []
        for d in web_dir.iterdir():
            f = d / "summary.txt" if (d / "summary.txt").exists() else d / "results.json"
            if f.exists():
                data["web_search"].append({
                    "query": d.name.replace("_", " "),
                    "content": f.read_text()[:3000],
                })

    # China search
    china_dir = data_dir / "china_search"
    if china_dir.exists():
        data["china_search"] = []
        for d in china_dir.iterdir():
            f = d / "summary.txt" if (d / "summary.txt").exists() else None
            if f and f.exists():
                data["china_search"].append({
                    "query": d.name.replace("_", " "),
                    "content": f.read_text()[:3000],
                })

    # Play Store reviews
    ps_dir = data_dir / "play_store"
    if ps_dir.exists():
        data["play_store"] = []
        for d in ps_dir.iterdir():
            f = d / "play_store_reviews.json"
            if f.exists():
                reviews = read_json(f) or {}
                app_reviews = reviews.get("reviews", [])[:100]
                data["play_store"].append({
                    "app": d.name,
                    "info": reviews.get("app_info", {}),
                    "reviews": app_reviews,
                    "total": len(reviews.get("reviews", [])),
                })

    # App Store reviews
    as_dir = data_dir / "app_store"
    if as_dir.exists():
        data["app_store"] = []
        for d in as_dir.iterdir():
            f = d / "reviews.json"
            if f.exists():
                reviews = read_json(f) or {}
                app_reviews = (reviews.get("reviews", []) if isinstance(reviews, dict) else reviews)[:100]
                data["app_store"].append({
                    "app": d.name,
                    "reviews": app_reviews,
                })

    # Reddit
    reddit_dir = data_dir / "reddit"
    if reddit_dir.exists():
        data["reddit"] = []
        for d in reddit_dir.iterdir():
            f = d / "posts.json"
            if f.exists():
                posts = read_json(f) or []
                data["reddit"].append({
                    "source": d.name.replace("_", " "),
                    "posts": posts[:30],
                })

    # YouTube
    yt_dir = data_dir / "youtube"
    if yt_dir.exists():
        data["youtube"] = []
        for item in yt_dir.iterdir():
            if item.suffix == ".json":
                data["youtube"].append(read_json(item) or {})
            elif item.is_dir():
                f = item / "results.json"
                if f.exists():
                    data["youtube"].append({"search": item.name, "results": read_json(f) or []})

    # Google Trends
    trends_dir = data_dir / "google_trends"
    if trends_dir.exists():
        files = list(trends_dir.glob("*.json"))
        if files:
            data["google_trends"] = read_json(files[0])

    # Trustpilot
    tp_dir = data_dir / "trustpilot"
    if tp_dir.exists():
        data["trustpilot"] = []
        for d in tp_dir.iterdir():
            f = d / "reviews.json"
            if f.exists():
                reviews = read_json(f) or {}
                data["trustpilot"].append({
                    "company": reviews.get("company", {}),
                    "reviews": reviews.get("reviews", [])[:50],
                })

    # Meta Ads
    meta_dir = data_dir / "meta_ads"
    if meta_dir.exists():
        data["meta_ads"] = []
        for d in meta_dir.iterdir():
            ads = []
            for f in d.glob("*.json"):
                ad = read_json(f)
                if ad:
                    ads.append(ad)
            if ads:
                data["meta_ads"].append({"brand": d.name, "ads": ads[:20]})

    return data


# ── Gemini synthesizer ─────────────────────────────────────────────────────────

def synthesize(config: dict, data: dict) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    topic      = config["topic"]
    discovery  = config.get("discovery", {})
    major_comp = config.get("competitors", {}).get("major", [])
    minor_comp = config.get("competitors", {}).get("minor", [])

    data_summary = json.dumps(data, ensure_ascii=False, indent=1)[:80000]

    prompt = f"""You are a senior market research analyst. Write a comprehensive market research report on: "{topic}"

## Context

### Market Discovery (pre-research)
Global: {discovery.get('global', '')[:2000]}
India: {discovery.get('india', '')[:2000]}
China: {discovery.get('china', '')[:1500]}

### Major Competitors
{json.dumps(major_comp, indent=1)}

### Minor Competitors
{json.dumps(minor_comp, indent=1)}

## Collected Data
{data_summary}

---

Write the report in Markdown with these 8 sections:

# {topic.title()} — Market Research Report

## 1. Executive Summary
2–3 paragraphs. Key market size, top players, major opportunity.

## 2. Market Overview
### Global
### India
### China
Market size, growth rates, key trends, regulatory context.

## 3. Competitor Landscape
### Global Players
### India Players
### China Players
For each major player: positioning, revenue/users, strengths, weaknesses.
Include a comparison table.

## 4. Consumer Voice
Synthesize App Store + Play Store + Trustpilot + Reddit reviews.
Top pain points (ranked). Top loved features. Sentiment by platform.

## 5. Content & Ads Intelligence
YouTube: what content works, top channels, messaging themes.
Meta Ads: ad formats, creative themes, CTAs, targeting signals.

## 6. Trends & Momentum
Google Trends analysis — rising vs falling keywords, geographic breakdowns.
Seasonal patterns if visible.

## 7. Opportunities & Gaps
- What India-specific needs are unmet?
- What China trends could move to India?
- White spaces in the market
- Pricing opportunities

## 8. Sources & Data
List all data sources used, with counts (e.g. "450 Play Store reviews across 3 apps").

---

Rules:
- Use specific numbers wherever data supports it
- Flag clearly when making inferences vs citing data
- Keep it actionable — built for a founder or VC making a decision
- Minimum 2000 words
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.3),
    )
    return response.text.strip()


# ── Entry point ────────────────────────────────────────────────────────────────

def phase3(config_path: str):
    config_file = Path(config_path)
    if not config_file.exists():
        print(f"Config not found: {config_path}")
        sys.exit(1)

    config   = json.loads(config_file.read_text())
    data_dir = config_file.parent / "data"

    print(f"\n{'='*60}")
    print(f"  Phase 3 — Synthesis")
    print(f"  Topic: {config['topic']}")
    print(f"{'='*60}\n")

    print("  Loading collected data...")
    data = load_data(data_dir)
    sources = {k: len(v) if isinstance(v, list) else 1 for k, v in data.items() if v}
    for src, count in sources.items():
        print(f"    {src}: {count} items")

    print("\n  Synthesizing report with Gemini (this takes ~30s)...")
    report = synthesize(config, data)

    report_path = config_file.parent / "report.md"
    report_path.write_text(report, encoding="utf-8")

    print(f"\n  Report saved → {report_path}")
    print(f"  Words: ~{len(report.split())}")
    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: uv run python phase3.py research/<slug>/config.json")
        sys.exit(1)
    phase3(sys.argv[1])
