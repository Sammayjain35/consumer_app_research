"""
China Web Search Tool — Baidu (Playwright) + DeepSeek synthesis
Scrapes Baidu for real-time Chinese web results, then feeds them to DeepSeek
for a synthesized Chinese market research report.

Usage:
    uv run python tools/china_search.py --query "companion app China market"
    uv run python tools/china_search.py --query "短视频市场 2025" --deep

Flags:
    --query    Search query (English or Chinese)
    --deep     Deep research mode — more thorough prompt
    --max      Max Baidu results to scrape (default: 10)
    --out      Output directory (default: data/china_search)

Requires:
    DEEPSEEK_API_KEY in .env
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


# ── Baidu scraper ──────────────────────────────────────────────────────────────

def scrape_baidu(query: str, max_results: int = 10) -> list[dict]:
    """Scrape Baidu search results using Playwright."""
    from playwright.sync_api import sync_playwright

    print(f"   ↳ Opening Baidu for: '{query}'...", flush=True)
    results = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
            )

            # Set Chinese locale to look more like a local browser
            page.set_extra_http_headers({
                "Accept-Language": "zh-CN,zh;q=0.9",
            })

            url = f"http://www.baidu.com/s?wd={query}&rn={max_results}"
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)

            # Extract results
            items = page.query_selector_all(".result, .result-op")
            for item in items[:max_results]:
                try:
                    # Title
                    title_el = item.query_selector("h3")
                    title = title_el.inner_text().strip() if title_el else ""

                    # Snippet / abstract
                    snippet_el = item.query_selector(".c-abstract, .content-right_8Zs40, .c-span9")
                    snippet = snippet_el.inner_text().strip() if snippet_el else ""

                    # URL — Baidu wraps links, get the displayed URL
                    url_el = item.query_selector(".c-showurl, .c-color-gray")
                    source_url = url_el.inner_text().strip() if url_el else ""

                    # Actual href (Baidu redirect)
                    link_el = item.query_selector("h3 a")
                    href = link_el.get_attribute("href") if link_el else ""

                    if title:
                        results.append({
                            "title":   title,
                            "snippet": snippet,
                            "url":     source_url,
                            "href":    href,
                        })
                        print(f"     {len(results):>2}. {title[:70]}")
                except Exception:
                    continue

            browser.close()

    except Exception as e:
        print(f"   ⚠️  Baidu scrape error: {e}")

    print(f"   ↳ {len(results)} Baidu results scraped")
    return results


# ── DeepSeek synthesis ─────────────────────────────────────────────────────────

def synthesize_with_deepseek(query: str, baidu_results: list[dict], deep: bool = False) -> str:
    """Send Baidu results to DeepSeek for synthesis into a research report."""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("❌ DEEPSEEK_API_KEY not set in .env", file=sys.stderr)
        sys.exit(1)

    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    # Format Baidu results as context
    baidu_context = ""
    if baidu_results:
        baidu_context = "## Baidu Search Results\n\n"
        for i, r in enumerate(baidu_results, 1):
            baidu_context += f"**{i}. {r['title']}**\n"
            if r["snippet"]:
                baidu_context += f"{r['snippet']}\n"
            if r["url"]:
                baidu_context += f"Source: {r['url']}\n"
            baidu_context += "\n"
    else:
        baidu_context = "## Baidu Search Results\n\n(No results scraped — Baidu may have blocked the request. Using DeepSeek knowledge only.)\n\n"

    if deep:
        prompt = f"""You are a Chinese market research expert with deep knowledge of China's tech, consumer, and business landscape.

Research topic: "{query}"

{baidu_context}

Based on the Baidu search results above AND your own deep knowledge of the Chinese market, provide a comprehensive research report:

1. **市场概况 (Market Overview)** — Key facts, market size, growth numbers
2. **主要玩家 (Key Players)** — Major Chinese companies, their market position, revenue if known
3. **最新动态 (Recent Developments)** — News, launches, funding from the past 12 months
4. **市场趋势 (Market Trends)** — What's growing, what's declining, regulatory landscape
5. **机遇与空白 (Opportunities & Gaps)** — Underserved segments, white spaces, entry angles
6. **对外国入局者的启示 (Implications for Foreign Entrants)** — What this means for non-Chinese companies

Write in English. Be specific with numbers and dates. Where Baidu results provide data, cite them."""
    else:
        prompt = f"""You are a Chinese market research expert.

Research topic: "{query}"

{baidu_context}

Based on the Baidu search results above AND your knowledge of the Chinese market, give a clear, factual summary covering: key facts, market size, major players, and recent developments. Write in English. Be specific."""

    print("   ↳ Sending to DeepSeek for synthesis...", flush=True)
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return response.choices[0].message.content


# ── Save ───────────────────────────────────────────────────────────────────────

def save(result: dict, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "results.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"  JSON → {json_path}")

    txt_path = output_dir / "summary.txt"
    lines = [
        f"Query:        {result['query']}",
        f"Mode:         {result['mode']}",
        f"Fetched:      {result['fetched_at']}",
        f"Baidu results:{result['baidu_results_count']}",
        "",
        result["summary"],
        "",
        "── Baidu Sources ────────────────────────────────────",
    ]
    for r in result["baidu_results"]:
        if r["title"]:
            lines.append(f"• {r['title']}")
            if r["url"]:
                lines.append(f"  {r['url']}")
    txt_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  TXT  → {txt_path}")


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Chinese web search via Baidu + DeepSeek")
    parser.add_argument("--query", required=True, help="Search query (English or Chinese)")
    parser.add_argument("--deep",  action="store_true", help="Deep research mode")
    parser.add_argument("--max",   type=int, default=10, help="Max Baidu results to scrape")
    parser.add_argument("--out",   default="data/china_search")
    args = parser.parse_args()

    print(f"\n🇨🇳 China Search: '{args.query}' (mode={'deep' if args.deep else 'standard'})")
    print("─" * 60)

    # Step 1 — Scrape Baidu
    print("\n📡 Step 1: Scraping Baidu...")
    baidu_results = scrape_baidu(args.query, args.max)

    # Step 2 — DeepSeek synthesis
    print("\n🤖 Step 2: DeepSeek synthesis...")
    summary = synthesize_with_deepseek(args.query, baidu_results, args.deep)
    print("   ↳ Done.")

    result = {
        "query":               args.query,
        "mode":                "deep" if args.deep else "standard",
        "fetched_at":          datetime.now().isoformat(),
        "baidu_results_count": len(baidu_results),
        "baidu_results":       baidu_results,
        "summary":             summary,
    }

    safe = args.query.replace(" ", "_")[:50]
    out  = Path(args.out) / safe
    save(result, out)

    print(f"\n✅ Done → {out}/")
    print("\n── Summary ──────────────────────────────────────────")
    print(summary)
    print("─────────────────────────────────────────────────────")


if __name__ == "__main__":
    main()
