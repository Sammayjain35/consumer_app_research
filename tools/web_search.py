"""
Web Search Tool — powered by Gemini + Google Search grounding
Real-time Google results synthesized by Gemini, with source citations.

Usage:
    uv run python tools/web_search.py --query "fantasy cricket market India 2025"
    uv run python tools/web_search.py --query "Dream11 revenue 2024" --deep

Flags:
    --query    Search query (required)
    --deep     Deep research mode — more thorough prompt, better for market research
    --out      Output directory (default: data/web_search)

Requires:
    GEMINI_API_KEY in .env
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def search(query: str, deep: bool = False) -> dict:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("❌ GEMINI_API_KEY not set in .env", file=sys.stderr)
        sys.exit(1)

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    if deep:
        prompt = f"""You are a professional market research analyst. Using Google Search, research the following topic thoroughly:

"{query}"

Provide a comprehensive report covering:
1. **Overview** — key facts, numbers, market size
2. **Key Players** — major companies, their positioning, revenue if available
3. **Recent Developments** — news, funding, launches from the last 12 months
4. **Market Trends** — what's growing, what's declining
5. **Opportunities & Gaps** — underserved segments, white spaces
6. **Sources** — cite sources inline

Be specific. Include numbers and dates wherever possible."""
    else:
        prompt = f"""Research this topic using Google Search and give a clear, factual summary:

"{query}"

Include key facts, numbers, notable players, and recent developments. Cite sources."""

    print(f"\n🔍 Searching: '{query}' (mode={'deep' if deep else 'standard'})", flush=True)
    print("   ↳ Querying Gemini + Google Search...", flush=True)

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        ),
    )

    # Extract grounding metadata
    sources = []
    search_queries = []
    try:
        grounding = response.candidates[0].grounding_metadata
        if grounding:
            search_queries = list(grounding.web_search_queries or [])
            for chunk in grounding.grounding_chunks or []:
                web = getattr(chunk, "web", None)
                if web:
                    sources.append({
                        "title": getattr(web, "title", ""),
                        "url":   getattr(web, "uri", ""),
                    })
    except Exception:
        pass

    print(f"   ↳ Done. {len(sources)} sources cited.")
    if search_queries:
        print(f"   ↳ Google searched: {', '.join(search_queries)}")

    return {
        "query":          query,
        "mode":           "deep" if deep else "standard",
        "fetched_at":     datetime.now().isoformat(),
        "google_queries": search_queries,
        "summary":        response.text,
        "sources":        sources,
    }


def save(result: dict, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "results.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"  JSON → {json_path}")

    txt_path = output_dir / "summary.txt"
    lines = [
        f"Query:   {result['query']}",
        f"Mode:    {result['mode']}",
        f"Fetched: {result['fetched_at']}",
        f"Google searched for: {', '.join(result['google_queries'])}",
        "",
        result["summary"],
        "",
        "── Sources ──────────────────────────────────────────",
    ]
    for s in result["sources"]:
        lines.append(f"• {s['title']}")
        lines.append(f"  {s['url']}")
    txt_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  TXT  → {txt_path}")


def main():
    parser = argparse.ArgumentParser(description="Web search via Gemini + Google")
    parser.add_argument("--query", required=True, help="Search query")
    parser.add_argument("--deep",  action="store_true", help="Deep research mode")
    parser.add_argument("--out",   default="data/web_search")
    args = parser.parse_args()

    result = search(args.query, args.deep)

    safe = args.query.replace(" ", "_")[:50]
    out  = Path(args.out) / safe
    save(result, out)

    print(f"\n✅ Done → {out}/")
    print("\n── Summary ──────────────────────────────────────────")
    print(result["summary"])
    print("─────────────────────────────────────────────────────")


if __name__ == "__main__":
    main()
