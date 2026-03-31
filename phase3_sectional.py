"""
Phase 3 — Sectional Synthesis
Generates one report section at a time. Discuss each before moving on.
At the end, compile everything into report.md + report.html.

Usage:
    uv run python phase3_sectional.py research/companion-apps/config.json --section 1
    uv run python phase3_sectional.py research/companion-apps/config.json --section 2
    ...
    uv run python phase3_sectional.py research/companion-apps/config.json --compile

Sections:
    1  Executive Summary
    2  Market Overview (Global / India / China)
    3  Competitor Landscape
    4  Consumer Voice (reviews + Reddit)
    5  Content & Ads Intelligence (YouTube + Meta Ads)
    6  Trends & Momentum (Google Trends)
    7  Opportunities & Gaps
    8  Sources & Data  ← auto-generated, no Gemini call
"""

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

SECTIONS = {
    1: "Executive Summary",
    2: "Market Overview",
    3: "Competitor Landscape",
    4: "Consumer Voice",
    5: "Content & Ads Intelligence",
    6: "Trends & Momentum",
    7: "Opportunities & Gaps",
    8: "Sources & Data",
}


# ── Data loaders ───────────────────────────────────────────────────────────────

def read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def load_web_search(data_dir: Path) -> list[dict]:
    results = []
    for folder in ["web_search", "china_search"]:
        d = data_dir / folder
        if not d.exists():
            continue
        for f in d.rglob("summary.txt"):
            results.append({"source": folder, "query": f.parent.name.replace("_", " "), "content": f.read_text()[:3000]})
        if not results:
            for f in d.rglob("results.json"):
                results.append({"source": folder, "query": f.parent.name.replace("_", " "), "content": f.read_text()[:3000]})
    return results


def load_play_store(data_dir: Path, reviews=True) -> list[dict]:
    apps = []
    ps_dir = data_dir / "play_store"
    if not ps_dir.exists():
        return apps
    for d in ps_dir.iterdir():
        f = d / "play_store_reviews.json"
        if not f.exists():
            continue
        raw = read_json(f) or {}
        all_reviews = raw.get("reviews", [])
        info = raw.get("app_info", {})
        entry = {"app": d.name, "info": info, "total_reviews": len(all_reviews)}
        if reviews:
            neg = sorted([r for r in all_reviews if r.get("rating", 5) <= 2 and r.get("review_text", "").strip()],
                         key=lambda x: x.get("thumbs_up", 0), reverse=True)[:6]
            pos = sorted([r for r in all_reviews if r.get("rating", 0) >= 4 and r.get("review_text", "").strip()],
                         key=lambda x: x.get("thumbs_up", 0), reverse=True)[:6]
            entry["negative"] = neg
            entry["positive"] = pos
        apps.append(entry)
    return apps


def load_app_store(data_dir: Path, reviews=True) -> list[dict]:
    apps = []
    as_dir = data_dir / "app_store"
    if not as_dir.exists():
        return apps
    for f in as_dir.rglob("reviews.json"):
        raw = read_json(f) or {}
        all_reviews = (raw.get("reviews", []) if isinstance(raw, dict) else raw)
        entry = {"app": f.parent.name, "total_reviews": len(all_reviews)}
        if reviews:
            entry["reviews"] = all_reviews[:60]
        apps.append(entry)
    return apps


def load_reddit(data_dir: Path) -> list[dict]:
    results = []
    reddit_dir = data_dir / "reddit"
    if not reddit_dir.exists():
        return results
    for f in reddit_dir.rglob("posts.json"):
        raw = read_json(f) or {}
        posts = raw.get("posts", raw) if isinstance(raw, dict) else raw
        top = sorted(posts, key=lambda x: x.get("score", 0), reverse=True)[:15]
        results.append({"source": f.parent.name.replace("_", " "), "posts": top})
    return results


def load_youtube(data_dir: Path) -> list[dict]:
    results = []
    yt_dir = data_dir / "youtube"
    if not yt_dir.exists():
        return results
    for f in yt_dir.rglob("*.json"):
        data = read_json(f)
        if data:
            results.append(data)
    return results


def load_google_trends(data_dir: Path) -> dict:
    trends_dir = data_dir / "google_trends"
    if not trends_dir.exists():
        return {}
    files = list(trends_dir.glob("*.json"))
    return read_json(files[0]) if files else {}


def load_meta_ads(data_dir: Path) -> list[dict]:
    brands = []
    meta_dir = data_dir / "meta_ads"
    if not meta_dir.exists():
        return brands
    for d in meta_dir.iterdir():
        if not d.is_dir():
            continue
        ads = []
        for f in d.glob("*.json"):
            ad = read_json(f)
            if ad:
                ads.append(ad)
        if ads:
            brands.append({"brand": d.name, "ads": ads[:20]})
    return brands


# ── Data formatters (turn raw data into focused text for Gemini) ────────────────

def fmt_web(items: list[dict], source_filter=None) -> str:
    lines = []
    for item in items:
        if source_filter and item["source"] != source_filter:
            continue
        lines.append(f"\n[{item['source'].upper()}] Query: {item['query']}\n{item['content'][:2500]}")
    return "\n".join(lines)


def fmt_play_store_info(apps: list[dict]) -> str:
    lines = []
    for app in apps:
        info = app.get("info", {})
        lines.append(
            f"\n{app['app']} | Score: {info.get('score', '?')} | "
            f"Installs: {info.get('installs', '?')} | "
            f"Reviews: {app['total_reviews']}"
        )
    return "\n".join(lines)


def fmt_play_store_reviews(apps: list[dict]) -> str:
    lines = []
    for app in apps:
        lines.append(f"\n=== {app['app']} ({app['total_reviews']} reviews) ===")
        for r in app.get("negative", []):
            lines.append(f"  [{r['rating']}★ NEG | +{r.get('thumbs_up',0)} helpful] \"{r['review_text'][:250]}\"")
        for r in app.get("positive", []):
            lines.append(f"  [{r['rating']}★ POS | +{r.get('thumbs_up',0)} helpful] \"{r['review_text'][:250]}\"")
    return "\n".join(lines)


def fmt_app_store_reviews(apps: list[dict]) -> str:
    lines = []
    for app in apps:
        lines.append(f"\n=== App Store: {app['app']} ===")
        for r in app.get("reviews", [])[:20]:
            text = r.get("review", r.get("content", r.get("body", "")))
            rating = r.get("rating") or r.get("score", "?")
            if text:
                lines.append(f"  [{rating}★] \"{str(text)[:250]}\"")
    return "\n".join(lines)


def fmt_reddit(sources: list[dict]) -> str:
    lines = []
    for src in sources:
        lines.append(f"\n=== Reddit: {src['source']} ===")
        for p in src["posts"]:
            lines.append(f"  [{p.get('score',0)} pts] \"{p['title']}\"")
            if p.get("text", "").strip():
                lines.append(f"    {p['text'][:300]}")
            for c in p.get("top_comments", [])[:3]:
                body = c.get("body", c.get("text", ""))
                if body.strip():
                    lines.append(f"    > [{c.get('score',0)} pts] \"{body[:200]}\"")
    return "\n".join(lines)


def fmt_youtube(items: list[dict]) -> str:
    lines = []
    for item in items:
        if item.get("search"):
            lines.append(f"\nYouTube Search: \"{item['search']}\"")
            for v in (item.get("results") or item.get("videos", []))[:8]:
                lines.append(f"  - \"{v.get('title','')}\" | {v.get('view_count', v.get('views',''))} views | {v.get('channel_title', v.get('channel',''))}")
        elif item.get("channel_info") or item.get("title"):
            ch = item.get("channel_info", item)
            lines.append(f"\nChannel: {ch.get('title','')} | Subs: {ch.get('subscriber_count','')} | Views: {ch.get('view_count','')}")
            for v in item.get("top_videos", [])[:8]:
                lines.append(f"  - \"{v.get('title','')}\" | {v.get('view_count','')} views")
    return "\n".join(lines)


def fmt_trends(trends: dict) -> str:
    if not trends:
        return "No trends data."
    lines = [f"Keywords: {', '.join(trends.get('keywords', []))}"]
    lines.append(f"Geo: {trends.get('geo', 'Global')}")
    for kw, vals in (trends.get("interest_over_time") or {}).items():
        if isinstance(vals, list):
            lines.append(f"  {kw} — recent: {vals[-8:]}")
    for kw, regions in list((trends.get("interest_by_region") or {}).items())[:5]:
        if isinstance(regions, dict):
            top = sorted(regions.items(), key=lambda x: x[1], reverse=True)[:5]
            lines.append(f"  {kw} top regions: {top}")
    return "\n".join(lines)


def fmt_meta_ads(brands: list[dict]) -> str:
    lines = []
    for brand in brands:
        lines.append(f"\n=== Meta Ads: {brand['brand']} ({len(brand['ads'])} ads) ===")
        for ad in brand["ads"]:
            analysis = ad.get("analysis", {}).get("raw_response", "")
            if analysis:
                lines.append(f"  {analysis[:700]}")
    return "\n".join(lines)


# ── Gemini call ────────────────────────────────────────────────────────────────

def call_gemini(prompt: str, section_name: str) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set in .env")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    print(f"  Calling Gemini for: {section_name}...")

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=16384,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    candidate = response.candidates[0]
    print(f"  Finish reason: {candidate.finish_reason}")
    return "".join(part.text for part in candidate.content.parts if hasattr(part, "text")).strip()


# ── Section generators ─────────────────────────────────────────────────────────

def gen_section_1(config: dict, data_dir: Path) -> str:
    topic = config["topic"]
    discovery = config.get("discovery", {})
    web = load_web_search(data_dir)

    prompt = f"""You are a senior market research analyst writing Section 1 of a report on: "{topic}"

Write ONLY the Executive Summary — 3 tight paragraphs.
- Para 1: Market size (global + India + China), growth rates, key players, headline numbers.
- Para 2: What the data actually shows about user behavior, monetization challenges, and engagement patterns.
- Para 3: The core opportunity in 2–3 sentences. Specific, not generic.

Rules:
- Every number must come from the data below. No invented stats.
- Name specific companies and products.
- No filler phrases like "in conclusion" or "it is evident that".

## Pre-Research Discovery
Global: {discovery.get('global', '')[:2000]}
India: {discovery.get('india', '')[:2000]}
China: {discovery.get('china', '')[:1000]}

## Web Search Data
{fmt_web(web)}

Write only the section content (no heading needed — it will be added automatically).
"""
    return call_gemini(prompt, "Executive Summary")


def gen_section_2(config: dict, data_dir: Path) -> str:
    topic = config["topic"]
    discovery = config.get("discovery", {})
    web = load_web_search(data_dir)
    trends = load_google_trends(data_dir)

    prompt = f"""You are a senior market research analyst writing Section 2 (Market Overview) for a report on: "{topic}"

Write three sub-sections: ### Global, ### India, ### China

For each:
- Market size with year, projected size, CAGR
- Key players and their scale
- User behavior patterns
- Regulatory context (where relevant)
- 1–2 sentences on what makes this geography distinct

Rules:
- Only use numbers from the data below.
- Be specific. Name companies, name regulations, name funding rounds.
- Do not pad. If you don't have data for something, skip it.

## Pre-Research Discovery
Global: {discovery.get('global', '')[:2500]}
India: {discovery.get('india', '')[:2500]}
China: {discovery.get('china', '')[:1500]}

## Web Search Data
{fmt_web(web)}

## Google Trends
{fmt_trends(trends)}

Write only the section content (no top-level heading needed).
"""
    return call_gemini(prompt, "Market Overview")


def gen_section_3(config: dict, data_dir: Path) -> str:
    topic = config["topic"]
    major = config.get("competitors", {}).get("major", [])
    minor = config.get("competitors", {}).get("minor", [])
    web = load_web_search(data_dir)
    ps_apps = load_play_store(data_dir, reviews=False)
    as_apps = load_app_store(data_dir, reviews=False)

    prompt = f"""You are a senior market research analyst writing Section 3 (Competitor Landscape) for a report on: "{topic}"

Structure:
1. A comparison table with columns: Competitor | Positioning | Play Store Rating | Installs | Key Strength | Key Weakness
2. For each MAJOR competitor: 2–3 sentences on positioning, what makes them distinct, and one specific weakness visible in the data.
3. A brief paragraph on MINOR competitors and emerging players.

Rules:
- Use exact ratings and install counts from the Play Store data below.
- Be direct about weaknesses. Name the specific issue, not vague language.
- Do not write about competitors not listed below.

## Competitors
Major: {json.dumps([c['name'] for c in major])}
Minor: {json.dumps([c['name'] for c in minor])}

## Play Store App Info
{fmt_play_store_info(ps_apps)}

## App Store Info
{', '.join(a['app'] for a in as_apps)} (total reviews: {', '.join(str(a['total_reviews']) for a in as_apps)})

## Web Search Context
{fmt_web(web)[:4000]}

Write only the section content (no top-level heading needed).
"""
    return call_gemini(prompt, "Competitor Landscape")


def gen_section_4(config: dict, data_dir: Path) -> str:
    topic = config["topic"]
    ps_apps = load_play_store(data_dir, reviews=True)
    as_apps = load_app_store(data_dir, reviews=True)
    reddit = load_reddit(data_dir)

    prompt = f"""You are a senior market research analyst writing Section 4 (Consumer Voice) for a report on: "{topic}"

This section must be built entirely from real user data. No synthesis or generalizations without a quote to back it.

Structure:
### Top Pain Points
List 5 pain points. Each must have:
- A clear label (e.g., "Subscription price shock")
- 2+ verbatim quotes from reviews, with app name and star rating
- Which apps this affects most

### What Users Love
List 5 things users genuinely value. Same format — label + quotes + which apps.

### Reddit Signals
- Top 5 Reddit posts by score (title + score)
- What users are actually debating or asking about
- Any India-specific patterns you notice

Rules:
- Quotes must be verbatim from the data below. Use quotation marks.
- Always name the app and star rating with each quote.
- Do not paraphrase reviews — quote them directly.
- If a review has high thumbs_up, flag it — it means many users agree.

## Play Store Reviews
{fmt_play_store_reviews(ps_apps)}

## App Store Reviews
{fmt_app_store_reviews(as_apps)}

## Reddit Posts
{fmt_reddit(reddit)}

Write only the section content (no top-level heading needed).
"""
    return call_gemini(prompt, "Consumer Voice")


def gen_section_5(config: dict, data_dir: Path) -> str:
    topic = config["topic"]
    yt = load_youtube(data_dir)
    meta = load_meta_ads(data_dir)

    prompt = f"""You are a senior market research analyst writing Section 5 (Content & Ads Intelligence) for a report on: "{topic}"

Structure:
### YouTube
- Which topics and formats are getting the most views in this space
- Specific video titles, view counts, and channels — cite them by name
- What content themes are competitors NOT making that users seem to want

### Meta Ads
- For each brand: what hook/angle they're using, what the CTA is, visual/emotional theme
- What messaging patterns appear across multiple brands (shows what's working)
- Any notable difference in how different competitors approach paid creative

Rules:
- Reference specific video titles and view counts.
- Describe Meta ad creative specifically — not "they run emotional ads" but what emotion, what scene, what copy.
- Draw comparisons between brands where the data supports it.

## YouTube Data
{fmt_youtube(yt)}

## Meta Ads Data
{fmt_meta_ads(meta)}

Write only the section content (no top-level heading needed).
"""
    return call_gemini(prompt, "Content & Ads Intelligence")


def gen_section_6(config: dict, data_dir: Path) -> str:
    topic = config["topic"]
    trends = load_google_trends(data_dir)
    yt = load_youtube(data_dir)

    prompt = f"""You are a senior market research analyst writing Section 6 (Trends & Momentum) for a report on: "{topic}"

Structure:
### Search Trends
- Which keywords are rising vs falling (cite specific keyword names)
- Regional breakdown — where is interest highest?
- Any seasonal patterns visible in the time series data

### Content Momentum
- Which topics are gaining traction on YouTube based on view counts
- What search queries are people using when looking for this category

Rules:
- Reference specific keyword names from the data, not generic labels.
- Cite actual region names from the trends data.
- If trend data is sparse, say so — don't pad.

## Google Trends
{fmt_trends(trends)}

## YouTube Search Results
{fmt_youtube(yt)}

Write only the section content (no top-level heading needed).
"""
    return call_gemini(prompt, "Trends & Momentum")


def gen_section_7(config: dict, data_dir: Path) -> str:
    topic = config["topic"]
    discovery = config.get("discovery", {})
    ps_apps = load_play_store(data_dir, reviews=True)
    reddit = load_reddit(data_dir)
    web = load_web_search(data_dir)

    # Condense reviews to just the most-upvoted pain points
    pain_signals = []
    for app in ps_apps:
        for r in app.get("negative", [])[:3]:
            pain_signals.append(f"[{app['app']} {r['rating']}★ +{r.get('thumbs_up',0)}] \"{r['review_text'][:200]}\"")

    prompt = f"""You are a senior market research analyst writing Section 7 (Opportunities & Gaps) for a report on: "{topic}"

Based only on evidence in the data, identify concrete opportunities. Every gap must be backed by a data signal.

Structure:
### Unmet User Needs
- What are users explicitly asking for that no current app provides?
- Cite reviews or Reddit posts as evidence.

### Pricing Opportunity
- What do users say about current pricing? Is there a price point they'd accept?
- Cite specific complaints about subscriptions or paywalls.

### India-Specific Gaps
- What patterns in the data suggest India is underserved specifically?
- Language, cultural, trust, or pricing factors.

### White Space
- Combinations of features or positioning that no competitor currently owns.
- Supported by the competitive landscape data.

Rules:
- Each opportunity must have at least one data signal cited.
- Do not write generic "there is an opportunity in AI" statements.
- Be specific about which competitor is NOT doing something.

## Top Pain Signals (high-upvote reviews)
{chr(10).join(pain_signals[:20])}

## Reddit Signals
{fmt_reddit(reddit)[:3000]}

## Market Context
India: {discovery.get('india', '')[:1500]}

## Web Research
{fmt_web(web)[:3000]}

Write only the section content (no top-level heading needed).
"""
    return call_gemini(prompt, "Opportunities & Gaps")


def gen_section_8(config: dict, data_dir: Path) -> str:
    """Auto-generate sources section — no Gemini call needed."""
    lines = ["### Data Collected\n"]
    checks = [
        ("web_search", "Web Search (DuckDuckGo + article extraction)"),
        ("china_search", "China Search (Baidu + DeepSeek)"),
        ("play_store", "Google Play Store Reviews"),
        ("app_store", "iOS App Store Reviews"),
        ("reddit", "Reddit Posts"),
        ("youtube", "YouTube"),
        ("google_trends", "Google Trends"),
        ("meta_ads", "Meta Ads Library"),
        ("trustpilot", "Trustpilot"),
    ]
    for folder, label in checks:
        d = data_dir / folder
        if d.exists():
            count = len(list(d.rglob("*.json")))
            lines.append(f"- **{label}**: {count} files")
    lines.append(f"\n_Config: `{config['slug']}`_")
    return "\n".join(lines)


# ── Save / load sections ───────────────────────────────────────────────────────

def sections_dir(config_file: Path) -> Path:
    d = config_file.parent / "sections"
    d.mkdir(exist_ok=True)
    return d


def save_section(config_file: Path, n: int, content: str):
    path = sections_dir(config_file) / f"section_{n:02d}.md"
    path.write_text(content, encoding="utf-8")
    print(f"  Saved → {path}")
    return path


def load_section(config_file: Path, n: int) -> str | None:
    path = sections_dir(config_file) / f"section_{n:02d}.md"
    return path.read_text(encoding="utf-8") if path.exists() else None


# ── Compile ────────────────────────────────────────────────────────────────────

def compile_report(config_file: Path, config: dict):
    from datetime import datetime

    slug = config["slug"]
    topic = config["topic"]
    sd = sections_dir(config_file)

    print(f"\n  Compiling sections into report...")
    missing = []
    parts = []

    for n, title in SECTIONS.items():
        path = sd / f"section_{n:02d}.md"
        if path.exists():
            parts.append(f"## {n}. {title}\n\n{path.read_text(encoding='utf-8')}")
        else:
            missing.append(n)

    if missing:
        print(f"  Warning: missing sections {missing} — they will be skipped in the report.")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    header = f"_Generated (sectional): {timestamp} | Topic: {topic}_\n\n---\n\n"
    full_report = header + f"# {topic.title()} — Market Research Report\n\n" + "\n\n---\n\n".join(parts)

    # Save markdown
    report_path = config_file.parent / "report.md"
    report_path.write_text(full_report, encoding="utf-8")
    print(f"  report.md → {report_path}")

    # Save HTML
    try:
        import markdown as md
        html_body = md.markdown(full_report, extensions=["tables", "fenced_code"])
    except ImportError:
        # Fallback: wrap in <pre> if markdown not installed
        html_body = f"<pre>{full_report}</pre>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{topic.title()} — Research Report</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 960px; margin: 40px auto; padding: 0 28px; color: #1a1a1a; line-height: 1.75; }}
  h1 {{ font-size: 2em; border-bottom: 3px solid #0055cc; padding-bottom: 12px; margin-bottom: 0.4em; }}
  h2 {{ font-size: 1.45em; color: #0055cc; margin-top: 2.5em; border-bottom: 1px solid #dde4ef; padding-bottom: 6px; }}
  h3 {{ font-size: 1.1em; color: #333; margin-top: 1.6em; }}
  p {{ margin: 0.8em 0; }}
  ul, ol {{ padding-left: 1.4em; }}
  li {{ margin: 0.3em 0; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1.2em 0; font-size: 0.93em; }}
  th {{ background: #0055cc; color: white; padding: 9px 13px; text-align: left; }}
  td {{ padding: 8px 13px; border-bottom: 1px solid #e4e8f0; vertical-align: top; }}
  tr:nth-child(even) {{ background: #f6f8fd; }}
  code {{ background: #eef1f7; padding: 2px 6px; border-radius: 4px; font-size: 0.88em; }}
  pre {{ background: #f3f5fa; padding: 14px; border-radius: 6px; overflow-x: auto; }}
  blockquote {{ border-left: 4px solid #0055cc; margin: 1em 0; padding: 4px 16px; color: #555; background: #f6f8fd; border-radius: 0 6px 6px 0; }}
  em {{ color: #666; }}
  hr {{ border: none; border-top: 1px solid #dde4ef; margin: 2.5em 0; }}
  .toc {{ background: #f6f8fd; border: 1px solid #dde4ef; border-radius: 8px; padding: 18px 24px; margin: 2em 0; }}
  .toc h4 {{ margin: 0 0 10px 0; color: #0055cc; font-size: 0.95em; text-transform: uppercase; letter-spacing: 0.05em; }}
  .toc ol {{ margin: 0; padding-left: 1.3em; }}
  .toc li {{ margin: 4px 0; font-size: 0.95em; }}
</style>
</head>
<body>
<div class="toc">
  <h4>Contents</h4>
  <ol>
    {"".join(f"<li>{title}</li>" for title in SECTIONS.values())}
  </ol>
</div>
{html_body}
</body>
</html>"""

    html_path = config_file.parent / "report.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"  report.html → {html_path}")
    print(f"  Words: ~{len(full_report.split())}")


# ── Entry point ────────────────────────────────────────────────────────────────

GENERATORS = {
    1: gen_section_1,
    2: gen_section_2,
    3: gen_section_3,
    4: gen_section_4,
    5: gen_section_5,
    6: gen_section_6,
    7: gen_section_7,
    8: gen_section_8,
}


def main():
    parser = argparse.ArgumentParser(description="Phase 3 — sectional synthesis")
    parser.add_argument("config", help="Path to config.json")
    parser.add_argument("--section", type=int, choices=range(1, 9), metavar="N", help="Section number to generate (1–8)")
    parser.add_argument("--compile", action="store_true", help="Compile all saved sections into report.md + report.html")
    parser.add_argument("--status", action="store_true", help="Show which sections have been generated")
    args = parser.parse_args()

    config_file = Path(args.config)
    if not config_file.exists():
        print(f"Config not found: {args.config}")
        sys.exit(1)

    config = json.loads(config_file.read_text())
    data_dir = config_file.parent / "data"
    slug = config["slug"]
    topic = config["topic"]

    print(f"\n{'='*60}")
    print(f"  Phase 3 Sectional — {topic}")
    print(f"{'='*60}")

    if args.status:
        print("\n  Section status:")
        sd = sections_dir(config_file)
        for n, title in SECTIONS.items():
            path = sd / f"section_{n:02d}.md"
            status = f"✓ ({path.stat().st_size} bytes)" if path.exists() else "✗ not generated"
            print(f"    [{n}] {title}: {status}")
        print()
        return

    if args.compile:
        compile_report(config_file, config)
        print(f"\n{'='*60}\n")
        return

    if not args.section:
        parser.print_help()
        print("\n  Tip: run --status to see which sections are done.\n")
        sys.exit(1)

    n = args.section
    title = SECTIONS[n]
    print(f"\n  Generating Section {n}: {title}\n")

    content = GENERATORS[n](config, data_dir)
    save_section(config_file, n, content)

    # Print to terminal so you can read + discuss it
    print(f"\n{'─'*60}")
    print(f"  SECTION {n}: {title}")
    print(f"{'─'*60}\n")
    print(content)
    print(f"\n{'─'*60}")
    print(f"  Done. Discuss, then run --section {n+1} when ready.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
