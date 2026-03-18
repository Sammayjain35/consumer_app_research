"""
Web Search + Content Extraction Tool
Search the web via DuckDuckGo (no API key) and extract article content.

Usage:
    uv run python tools/web_search.py --query "ramayan app india subscription" --max 10
    uv run python tools/web_search.py --query "astrology startup india revenue" --max 10 --extract
    uv run python tools/web_search.py --url "https://example.com/article" --extract

Flags:
    --query    Search query
    --max      Max search results (default: 10)
    --extract  Also fetch and extract full text from each result URL
    --url      Extract content from a specific URL
    --out      Output directory (default: data/web_search)
"""
import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus, urlencode

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
DDG_URL = "https://html.duckduckgo.com/html/"


# ── Search ────────────────────────────────────────────────────────────────────

def search(query: str, max_results: int = 10) -> list:
    """Search DuckDuckGo and return structured results."""
    print(f"\n🔍 Searching: '{query}'")
    results = []
    try:
        r = requests.post(DDG_URL, data={"q": query, "b": ""}, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "lxml")

        for result in soup.select(".result"):
            title_el = result.select_one(".result__title a")
            snippet_el = result.select_one(".result__snippet")
            if not title_el:
                continue
            href = title_el.get("href", "")
            # DuckDuckGo wraps URLs — extract the real URL
            if "uddg=" in href:
                import urllib.parse
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                href = qs.get("uddg", [href])[0]

            results.append({
                "title":   title_el.get_text(strip=True),
                "url":     href,
                "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                "content": None,
            })
            print(f"  {len(results):>2}. {title_el.get_text(strip=True)[:80]}")

            if len(results) >= max_results:
                break
    except Exception as e:
        print(f"  ⚠️  Search error: {e}")

    print(f"\n  ✅ {len(results)} results found")
    return results


# ── Extract ───────────────────────────────────────────────────────────────────

def extract_content(url: str) -> str:
    """Extract readable text from a URL."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")

        # Remove noise
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
            tag.decompose()

        # Try article body first
        for selector in ["article", "main", ".content", ".post-content", ".entry-content", "#content"]:
            el = soup.select_one(selector)
            if el:
                text = el.get_text(separator="\n", strip=True)
                if len(text) > 200:
                    return _clean_text(text)[:5000]

        # Fallback: all paragraphs
        paragraphs = soup.find_all("p")
        text = "\n".join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 50)
        return _clean_text(text)[:5000]
    except Exception as e:
        return f"[Error extracting content: {e}]"


def _clean_text(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ── Save ──────────────────────────────────────────────────────────────────────

def save(name: str, results: list, query: str, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "query":      query,
        "searched_at": datetime.now().isoformat(),
        "total":      len(results),
        "results":    results,
    }
    path = output_dir / "results.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"  JSON → {path}")

    # Also save plain text summary for easy reading
    txt_path = output_dir / "summary.txt"
    with open(txt_path, "w") as f:
        f.write(f"Query: {query}\n")
        f.write(f"Date:  {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        for i, r in enumerate(results, 1):
            f.write(f"{'='*60}\n")
            f.write(f"{i}. {r['title']}\n")
            f.write(f"   {r['url']}\n\n")
            f.write(f"{r['snippet']}\n\n")
            if r.get("content"):
                f.write(f"Full content:\n{r['content'][:2000]}\n\n")
    print(f"  TXT  → {txt_path}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Web search + content extraction tool")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--query", help="Search query")
    group.add_argument("--url",   help="Extract content from a specific URL")
    parser.add_argument("--max",     type=int, default=10)
    parser.add_argument("--extract", action="store_true", help="Fetch full content from each result")
    parser.add_argument("--out",     default="data/web_search")
    args = parser.parse_args()

    if args.url:
        print(f"\n📄 Extracting: {args.url}")
        content = extract_content(args.url)
        print(content[:2000])
        out = Path(args.out) / "extracted"
        out.mkdir(parents=True, exist_ok=True)
        (out / "content.txt").write_text(content)
        print(f"\n✅ Saved → {out}/content.txt")
        return

    results = search(args.query, args.max)

    if args.extract and results:
        print(f"\n📄 Extracting content from {len(results)} URLs...")
        for i, result in enumerate(results, 1):
            if result["url"].startswith("http"):
                print(f"  [{i}/{len(results)}] {result['url'][:60]}...", end=" ", flush=True)
                result["content"] = extract_content(result["url"])
                print(f"✅ ({len(result['content'])} chars)")
                time.sleep(0.5)

    safe = args.query.replace(" ", "_")[:40]
    out  = Path(args.out) / safe
    save(safe, results, args.query, out)
    print(f"\n✅ Done → {out}/")


if __name__ == "__main__":
    main()
