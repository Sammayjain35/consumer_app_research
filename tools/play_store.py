"""
Play Store Review Scraper
Usage:
    uv run python review_scraper/scrape_play_reviews.py <play_store_url> [--max 500] [--country in] [--lang en]

Example:
    uv run python review_scraper/scrape_play_reviews.py "https://play.google.com/store/apps/details?id=com.flyrapp.ai" --max 500
"""

import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from google_play_scraper import Sort, reviews


# ─── URL / ID helpers ────────────────────────────────────────────────────────

def extract_package_id(url_or_id: str) -> str:
    """Accept either a full Play Store URL or a bare package ID."""
    if url_or_id.startswith("http"):
        parsed = urlparse(url_or_id)
        qs = parse_qs(parsed.query)
        if "id" not in qs:
            raise ValueError(f"Could not find ?id= in URL: {url_or_id}")
        return qs["id"][0]
    return url_or_id  # already a package ID


# ─── Core scraper ────────────────────────────────────────────────────────────

def scrape_reviews(
    package_id: str,
    max_reviews: int = 500,
    country: str = "in",
    lang: str = "en",
) -> list[dict]:
    """
    Fetch reviews from Play Store in batches of 200.
    Returns a flat list of review dicts.
    """
    all_reviews = []
    token = None
    batch_size = 200

    print(f"\nFetching reviews for: {package_id}")
    print(f"Country: {country} | Language: {lang} | Max: {max_reviews}")
    print("─" * 50)

    while len(all_reviews) < max_reviews:
        remaining = max_reviews - len(all_reviews)
        fetch_count = min(batch_size, remaining)

        try:
            batch, token = reviews(
                package_id,
                lang=lang,
                country=country,
                sort=Sort.NEWEST,
                count=fetch_count,
                continuation_token=token,
            )
        except Exception as e:
            print(f"Error fetching batch: {e}")
            break

        if not batch:
            print("No more reviews available.")
            break

        all_reviews.extend(batch)
        print(f"  Fetched {len(all_reviews)} reviews so far...")

        if token is None:
            print("Reached end of all available reviews.")
            break

        time.sleep(0.5)  # polite delay between batches

    print(f"\nTotal fetched: {len(all_reviews)} reviews")
    return all_reviews


# ─── Serialise ───────────────────────────────────────────────────────────────

def serialise_review(r: dict) -> dict:
    """Convert a raw review dict to JSON-serialisable form."""
    return {
        "review_id": r.get("reviewId"),
        "user_name": r.get("userName"),
        "rating": r.get("score"),          # 1–5
        "date": r.get("at").isoformat() if r.get("at") else None,
        "review_text": r.get("content"),
        "thumbs_up": r.get("thumbsUpCount", 0),
        "app_version": r.get("appVersion"),
        "reply_text": r.get("replyContent"),
        "reply_date": r.get("repliedAt").isoformat() if r.get("repliedAt") else None,
    }


# ─── Save ────────────────────────────────────────────────────────────────────

def save_results(package_id: str, raw_reviews: list[dict], output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)

    clean = [serialise_review(r) for r in raw_reviews]

    # JSON
    json_path = output_dir / "play_store_reviews.json"
    metadata = {
        "package_id": package_id,
        "scraped_at": datetime.now().isoformat(),
        "total_reviews": len(clean),
        "reviews": clean,
    }
    json_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
    print(f"JSON saved → {json_path}")

    # CSV
    csv_path = output_dir / "play_store_reviews.csv"
    if clean:
        fieldnames = list(clean[0].keys())
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(clean)
        print(f"CSV saved  → {csv_path}")

    # Quick stats
    print_stats(clean)


def print_stats(reviews: list[dict]):
    if not reviews:
        return
    ratings = [r["rating"] for r in reviews if r["rating"]]
    avg = sum(ratings) / len(ratings) if ratings else 0
    dist = {i: ratings.count(i) for i in range(1, 6)}

    print("\n── Rating distribution ──────────────────────")
    for star in range(5, 0, -1):
        bar = "█" * (dist[star] * 30 // max(dist.values(), default=1))
        print(f"  {star}★  {bar} {dist[star]}")
    print(f"\n  Average rating : {avg:.2f}")
    print(f"  Total reviews  : {len(reviews)}")
    print("─────────────────────────────────────────────")


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Scrape Play Store reviews for a given app URL or package ID"
    )
    parser.add_argument(
        "app",
        help="Full Play Store URL or bare package ID (e.g. com.flyrapp.ai)",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=500,
        help="Maximum number of reviews to fetch (default: 500)",
    )
    parser.add_argument(
        "--country",
        default="in",
        help="Two-letter country code (default: in for India)",
    )
    parser.add_argument(
        "--lang",
        default="en",
        help="Language code (default: en). Use 'hi' for Hindi.",
    )
    args = parser.parse_args()

    try:
        package_id = extract_package_id(args.app)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    raw = scrape_reviews(
        package_id,
        max_reviews=args.max,
        country=args.country,
        lang=args.lang,
    )

    if not raw:
        print("No reviews fetched. Check the package ID and try again.")
        sys.exit(1)

    output_dir = Path("data/play_store") / package_id

    save_results(package_id, raw, output_dir)
    print(f"\nDone. All files in: {output_dir}")


if __name__ == "__main__":
    main()
