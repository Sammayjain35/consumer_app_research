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
        for f in web_dir.rglob("summary.txt"):
            data["web_search"].append({
                "query": f.parent.name.replace("_", " "),
                "content": f.read_text()[:3000],
            })
        if not data["web_search"]:  # fallback to results.json
            for f in web_dir.rglob("results.json"):
                data["web_search"].append({
                    "query": f.parent.name.replace("_", " "),
                    "content": f.read_text()[:3000],
                })

    # China search
    china_dir = data_dir / "china_search"
    if china_dir.exists():
        data["china_search"] = []
        for f in china_dir.rglob("summary.txt"):
            data["china_search"].append({
                "query": f.parent.name.replace("_", " "),
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
        for f in as_dir.rglob("reviews.json"):
            reviews = read_json(f) or {}
            app_reviews = (reviews.get("reviews", []) if isinstance(reviews, dict) else reviews)[:100]
            data["app_store"].append({
                "app": f.parent.name,
                "reviews": app_reviews,
            })

    # Reddit
    reddit_dir = data_dir / "reddit"
    if reddit_dir.exists():
        data["reddit"] = []
        for f in reddit_dir.rglob("posts.json"):
            raw = read_json(f) or {}
            posts = raw.get("posts", raw) if isinstance(raw, dict) else raw
            data["reddit"].append({
                "source": f.parent.name.replace("_", " "),
                "posts": posts[:30],
            })

    # YouTube
    yt_dir = data_dir / "youtube"
    if yt_dir.exists():
        data["youtube"] = []
        for f in yt_dir.rglob("*.json"):
            data["youtube"].append(read_json(f) or {})

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
        for f in tp_dir.rglob("reviews.json"):
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


# ── Data pre-processor ─────────────────────────────────────────────────────────

def preprocess(data: dict) -> str:
    """Convert raw collected data into a signal-rich text summary for Gemini."""
    sections = []

    # ── Web / China search ────────────────────────────────────────────────────
    for key, label in [("web_search", "WEB SEARCH"), ("china_search", "CHINA SEARCH")]:
        items = data.get(key, [])
        if items:
            sections.append(f"=== {label} ===")
            for item in items:
                sections.append(f"Query: {item['query']}\n{item['content'][:2000]}\n")

    # ── Play Store reviews ────────────────────────────────────────────────────
    ps = data.get("play_store", [])
    if ps:
        sections.append("=== PLAY STORE REVIEWS ===")
        for app in ps:
            reviews = app.get("reviews", [])
            if not reviews:
                continue
            ratings = [r["rating"] for r in reviews if r.get("rating")]
            avg = sum(ratings) / len(ratings) if ratings else 0
            dist = {i: ratings.count(i) for i in range(1, 6)}
            # top negative and positive quotes
            neg = sorted([r for r in reviews if r.get("rating", 5) <= 2 and r.get("review_text", "").strip()],
                         key=lambda x: x.get("thumbs_up", 0), reverse=True)[:5]
            pos = sorted([r for r in reviews if r.get("rating", 0) >= 4 and r.get("review_text", "").strip()],
                         key=lambda x: x.get("thumbs_up", 0), reverse=True)[:5]
            info = app.get("info", {})
            sections.append(
                f"\nApp: {app['app']} | Rating: {avg:.1f}/5 ({len(ratings)} reviews) | "
                f"Dist: {dist} | Score: {info.get('score','')} | Installs: {info.get('installs','')}"
            )
            if neg:
                sections.append("  TOP NEGATIVE REVIEWS:")
                for r in neg:
                    sections.append(f"    [{r['rating']}★] \"{r['review_text'][:200]}\" (+{r.get('thumbs_up',0)} helpful)")
            if pos:
                sections.append("  TOP POSITIVE REVIEWS:")
                for r in pos:
                    sections.append(f"    [{r['rating']}★] \"{r['review_text'][:200]}\" (+{r.get('thumbs_up',0)} helpful)")

    # ── App Store reviews ─────────────────────────────────────────────────────
    apps = data.get("app_store", [])
    if apps:
        sections.append("\n=== APP STORE REVIEWS ===")
        for app in apps:
            reviews = app.get("reviews", [])
            if not reviews:
                continue
            ratings = [r.get("rating", r.get("score", 0)) for r in reviews if r.get("rating") or r.get("score")]
            avg = sum(ratings) / len(ratings) if ratings else 0
            neg = [r for r in reviews if (r.get("rating") or r.get("score", 5)) <= 2][:5]
            pos = [r for r in reviews if (r.get("rating") or r.get("score", 0)) >= 4][:5]
            sections.append(f"\nApp: {app['app']} | Avg: {avg:.1f}/5 ({len(ratings)} reviews)")
            for label2, items2 in [("NEGATIVE", neg), ("POSITIVE", pos)]:
                for r in items2:
                    text = r.get("review", r.get("content", r.get("body", "")))
                    rating = r.get("rating") or r.get("score", "?")
                    if text:
                        sections.append(f"  [{rating}★] \"{str(text)[:200]}\"")

    # ── Reddit ────────────────────────────────────────────────────────────────
    reddit = data.get("reddit", [])
    if reddit:
        sections.append("\n=== REDDIT POSTS & COMMENTS ===")
        for source in reddit:
            posts = source.get("posts", [])
            if not posts:
                continue
            sections.append(f"\nSource: {source['source']} ({len(posts)} posts)")
            top_posts = sorted(posts, key=lambda x: x.get("score", 0), reverse=True)[:8]
            for p in top_posts:
                sections.append(f"  [{p.get('score',0)} pts] \"{p['title']}\"")
                if p.get("text", "").strip():
                    sections.append(f"    {p['text'][:300]}")
                comments = p.get("top_comments", [])[:3]
                for c in comments:
                    body = c.get("body", c.get("text", ""))
                    if body.strip():
                        sections.append(f"    > Comment ({c.get('score',0)} pts): \"{body[:200]}\"")

    # ── YouTube ───────────────────────────────────────────────────────────────
    yt = data.get("youtube", [])
    if yt:
        sections.append("\n=== YOUTUBE ===")
        for item in yt:
            if item.get("search"):
                results = item.get("results", item.get("videos", []))[:5]
                sections.append(f"\nSearch: {item['search']}")
                for v in results:
                    sections.append(f"  - \"{v.get('title','')}\" | {v.get('view_count',v.get('views',''))} views | {v.get('channel_title',v.get('channel',''))}")
            elif item.get("channel_info") or item.get("title"):
                ch = item.get("channel_info", item)
                sections.append(f"\nChannel: {ch.get('title','')} | Subs: {ch.get('subscriber_count','')} | Views: {ch.get('view_count','')}")
                for v in item.get("top_videos", [])[:5]:
                    sections.append(f"  - \"{v.get('title','')}\" | {v.get('view_count','')} views")

    # ── Google Trends ─────────────────────────────────────────────────────────
    trends = data.get("google_trends")
    if trends:
        sections.append("\n=== GOOGLE TRENDS ===")
        keywords = trends.get("keywords", [])
        sections.append(f"Keywords tracked: {', '.join(keywords)}")
        geo = trends.get("geo", "")
        if geo:
            sections.append(f"Geography: {geo}")
        interest = trends.get("interest_over_time", {})
        if interest:
            # Show last few data points per keyword
            for kw, values in list(interest.items())[:5]:
                if isinstance(values, list):
                    recent = values[-6:]
                    sections.append(f"  {kw}: recent trend = {recent}")
        regional = trends.get("interest_by_region", {})
        if regional:
            sections.append("Top regions:")
            for kw, regions in list(regional.items())[:3]:
                top_r = sorted(regions.items(), key=lambda x: x[1], reverse=True)[:5] if isinstance(regions, dict) else []
                sections.append(f"  {kw}: {top_r}")

    # ── Meta Ads ──────────────────────────────────────────────────────────────
    meta = data.get("meta_ads", [])
    if meta:
        sections.append("\n=== META ADS ===")
        for brand in meta:
            ads = brand.get("ads", [])
            sections.append(f"\nBrand: {brand['brand']} ({len(ads)} ads)")
            for ad in ads[:10]:
                analysis = ad.get("analysis", {}).get("raw_response", "")
                media = ad.get("media", ad.get("video", {}))
                ad_type = media.get("type", "video")
                if analysis:
                    sections.append(f"  Ad ({ad_type}): {analysis[:600]}")

    # ── Trustpilot ────────────────────────────────────────────────────────────
    tp = data.get("trustpilot", [])
    if tp:
        sections.append("\n=== TRUSTPILOT ===")
        for company in tp:
            info = company.get("company", {})
            reviews = company.get("reviews", [])
            sections.append(f"\n{info.get('name','')} | Score: {info.get('score','')} | {info.get('review_count','')} reviews")
            for r in reviews[:5]:
                sections.append(f"  [{r.get('rating','')}★] \"{r.get('text','')[:200]}\"")

    return "\n".join(sections)


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

    data_summary = preprocess(data)

    prompt = f"""You are a senior market research analyst. Write a comprehensive, data-driven market research report on: "{topic}"

CRITICAL RULES — YOU MUST FOLLOW THESE:
1. Every claim must be backed by a specific data point from the collected data below.
2. Quote real user reviews verbatim (use quotation marks). Name the app and star rating.
3. Cite Reddit posts by title and score. Quote actual top comments.
4. Reference YouTube video titles, view counts, and channels by name.
5. Use Google Trends data with actual keyword names and regional breakdowns.
6. Reference Meta Ad creative details (hooks, CTAs, visual style) from the ad analyses provided.
7. DO NOT write generic market-research boilerplate. If you don't have data for something, say so explicitly instead of making it up.
8. Be specific about which competitor has which problem. Not "some apps" — name them.

## Market Discovery (pre-research context)
Global: {discovery.get('global', '')[:2000]}
India: {discovery.get('india', '')[:2000]}
China: {discovery.get('china', '')[:1500]}

## Competitors Being Researched
Major: {json.dumps([c['name'] for c in major_comp])}
Minor: {json.dumps([c['name'] for c in minor_comp])}

## COLLECTED DATA (cite from this directly)
{data_summary}

---

Write the full report in Markdown:

# {topic.title()} — Market Research Report

## 1. Executive Summary
2–3 paragraphs. Specific numbers, named players, concrete opportunity.

## 2. Market Overview
### Global
### India
### China
Market size with sources, growth rates, key trends, regulatory context.

## 3. Competitor Landscape
### Major Players
For each major competitor: positioning, rating/reviews data, key strengths, key weaknesses. Include a comparison table.

## 4. Consumer Voice
THIS SECTION MUST BE ENTIRELY FROM REVIEW DATA. Rules:
- List top 5 pain points, each with 2+ verbatim quotes naming the app and star rating
- List top 5 loved features, each with 2+ verbatim quotes
- Highlight Reddit posts with highest scores and what users are saying
- Note any patterns specific to Indian users if visible

## 5. Content & Ads Intelligence
- YouTube: cite specific video titles, view counts, channels
- Meta Ads: describe specific ad hooks, CTAs, and creative themes from the Gemini analyses

## 6. Trends & Momentum
- Google Trends: name specific keywords, show which are rising/falling, cite top regions

## 7. Opportunities & Gaps
Based only on the data above:
- India-specific unmet needs (cite reviews/Reddit)
- White spaces (what users are asking for that no app provides)
- Pricing opportunities (what users complain about regarding cost)

## 8. Sources & Data
List every data source with exact counts.
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=65536,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    candidate = response.candidates[0]
    finish_reason = candidate.finish_reason
    print(f"\n  Gemini finish_reason: {finish_reason}")
    text = "".join(part.text for part in candidate.content.parts if hasattr(part, "text"))
    return text.strip()


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

    from datetime import datetime
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    header = f"_Generated: {timestamp} | Sources: {', '.join(f'{k} ({v})' for k, v in sources.items())}_\n\n---\n\n"
    report = header + report

    report_path = config_file.parent / "report.md"
    report_path.write_text(report, encoding="utf-8")

    # HTML export
    import markdown as md
    html_body = md.markdown(report, extensions=["tables", "fenced_code"])
    topic_title = config["topic"].title()
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{topic_title} — Research Report</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 900px; margin: 40px auto; padding: 0 24px; color: #1a1a1a; line-height: 1.7; }}
  h1 {{ font-size: 2em; border-bottom: 3px solid #0066cc; padding-bottom: 12px; }}
  h2 {{ font-size: 1.4em; color: #0066cc; margin-top: 2em; border-bottom: 1px solid #e0e0e0; padding-bottom: 6px; }}
  h3 {{ font-size: 1.1em; color: #333; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1em 0; }}
  th {{ background: #0066cc; color: white; padding: 8px 12px; text-align: left; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #e0e0e0; }}
  tr:nth-child(even) {{ background: #f7f9fc; }}
  code {{ background: #f0f0f0; padding: 2px 6px; border-radius: 3px; font-size: 0.9em; }}
  blockquote {{ border-left: 4px solid #0066cc; margin: 0; padding: 0 16px; color: #555; }}
  em {{ color: #666; }}
  hr {{ border: none; border-top: 1px solid #e0e0e0; margin: 2em 0; }}
</style>
</head>
<body>
{html_body}
</body>
</html>"""
    html_path = config_file.parent / "report.html"
    html_path.write_text(html, encoding="utf-8")

    print(f"\n  Report saved → {report_path}")
    print(f"  HTML saved  → {html_path}")
    print(f"  Words: ~{len(report.split())}")
    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: uv run python phase3.py research/<slug>/config.json")
        sys.exit(1)
    phase3(sys.argv[1])
