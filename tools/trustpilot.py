"""
Trustpilot Review Scraper
Scrapes competitor reviews from Trustpilot using Playwright.

Usage:
    uv run python tools/trustpilot.py --company astrotalk --max 200
    uv run python tools/trustpilot.py --company kiwico.com --max 100
    uv run python tools/trustpilot.py --search "astrology app" --max 5

Flags:
    --company  Trustpilot company slug (e.g. astrotalk, kiwico.com)
    --search   Search Trustpilot for a company name
    --max      Max reviews to scrape (default: 100)
    --out      Output directory (default: data/trustpilot)
"""
import argparse
import csv
import json
import re
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright


TRUSTPILOT_BASE = "https://www.trustpilot.com"


# ── Scrape company info + reviews ─────────────────────────────────────────────

def scrape_company(slug: str, max_reviews: int = 100) -> dict:
    """Scrape reviews for a company from Trustpilot."""
    url = f"{TRUSTPILOT_BASE}/review/{slug}"
    print(f"\n⭐ Scraping Trustpilot: {slug}")
    print(f"   URL: {url}")

    reviews = []
    company_info = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        page_num = 1

        while len(reviews) < max_reviews:
            page_url = f"{url}?page={page_num}" if page_num > 1 else url
            try:
                page.goto(page_url, wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(1500)
            except Exception as e:
                print(f"  ⚠️  Page load error: {e}")
                break

            # Extract from __NEXT_DATA__ JSON (most reliable — Trustpilot is Next.js)
            try:
                next_data = page.evaluate("() => JSON.parse(document.getElementById('__NEXT_DATA__').textContent)")
                props = next_data.get("props", {}).get("pageProps", {})

                # Company info (first page only)
                if page_num == 1:
                    biz = props.get("businessUnit", {})
                    company_info = {
                        "name":       biz.get("displayName", slug),
                        "score":      biz.get("trustScore"),
                        "stars":      biz.get("stars"),
                        "rating_count": biz.get("numberOfReviews") if isinstance(biz.get("numberOfReviews"), int) else biz.get("numberOfReviews", {}).get("total"),
                        "url":        page_url,
                        "scraped_at": datetime.now().isoformat(),
                    }
                    print(f"  {company_info['name']} | Score: {company_info['score']} | Total reviews: {company_info['rating_count']}")

                # Reviews
                for r in props.get("reviews", []):
                    if len(reviews) >= max_reviews:
                        break
                    reviews.append({
                        "review_id":   r.get("id", ""),
                        "title":       r.get("title", ""),
                        "review_text": r.get("text", ""),
                        "rating":      r.get("rating"),
                        "date":        r.get("dates", {}).get("publishedDate", ""),
                        "language":    r.get("language", ""),
                        "verified":    r.get("isVerified", False),
                    })

                print(f"  Page {page_num}: {len(reviews)} reviews so far", end="\r", flush=True)

                # Check if more pages — pagination is nested inside filters
                pagination = props.get("filters", {}).get("pagination", {})
                total_pages = pagination.get("totalPages", 1)
                if page_num >= total_pages:
                    break

            except Exception as e:
                print(f"  ⚠️  Could not parse page data: {e}")
                break

            page_num += 1
            time.sleep(0.8)

        browser.close()

    print(f"\n  ✅ {len(reviews)} reviews scraped")
    return {"company": company_info, "reviews": reviews}


# ── Search ────────────────────────────────────────────────────────────────────

def search_companies(query: str, max_results: int = 5) -> list:
    """Search Trustpilot for companies matching a query."""
    print(f"\n🔍 Searching Trustpilot: '{query}'")
    results = []
    url = f"{TRUSTPILOT_BASE}/search?query={query.replace(' ', '+')}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)
            cards = page.query_selector_all("[class*='businessUnitResult']")
            for card in cards[:max_results]:
                link = card.query_selector("a")
                name = card.query_selector("[class*='name']") or card.query_selector("p")
                score = card.query_selector("[class*='score']") or card.query_selector("[data-rating]")
                if link:
                    href = link.get_attribute("href") or ""
                    slug = href.replace("/review/", "").strip("/")
                    results.append({
                        "slug":  slug,
                        "name":  name.inner_text().strip() if name else slug,
                        "url":   f"{TRUSTPILOT_BASE}{href}",
                        "score": score.inner_text().strip() if score else None,
                    })
                    print(f"  {slug}: {name.inner_text().strip() if name else ''}")
        except Exception as e:
            print(f"  ⚠️  {e}")
        browser.close()

    return results


# ── Save ──────────────────────────────────────────────────────────────────────

def save(slug: str, data: dict, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "reviews.json"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"  JSON → {json_path}")

    reviews = data.get("reviews", [])
    if reviews:
        csv_path = output_dir / "reviews.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(reviews[0].keys()))
            writer.writeheader()
            writer.writerows(reviews)
        print(f"  CSV  → {csv_path}")

        ratings = [r["rating"] for r in reviews if r.get("rating")]
        if ratings:
            avg = sum(ratings) / len(ratings)
            dist = {i: ratings.count(i) for i in range(1, 6)}
            print("\n  ── Rating distribution ──")
            for star in range(5, 0, -1):
                bar = "█" * (dist[star] * 25 // max(dist.values(), default=1))
                print(f"    {star}★  {bar} {dist[star]}")
            print(f"\n  Average: {avg:.2f} | Total: {len(ratings)}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Trustpilot review scraper")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--company", help="Trustpilot company slug (e.g. astrotalk)")
    group.add_argument("--search",  help="Search for company by name")
    parser.add_argument("--max", type=int, default=100)
    parser.add_argument("--out", default="data/trustpilot")
    args = parser.parse_args()

    if args.search:
        results = search_companies(args.search, args.max)
        out = Path(args.out) / "search"
        out.mkdir(parents=True, exist_ok=True)
        (out / "results.json").write_text(json.dumps(results, indent=2))
        print(f"\n✅ {len(results)} companies → {out}/results.json")
        return

    data = scrape_company(args.company, args.max)
    out  = Path(args.out) / args.company
    save(args.company, data, out)
    print(f"\n✅ Done → {out}/")


if __name__ == "__main__":
    main()
