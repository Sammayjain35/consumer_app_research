"""
Google Play Store Scraper
Scrapes reviews and app metadata for any Play Store app.

Usage:
    uv run python tools/play_store.py com.example.app --max 500
    uv run python tools/play_store.py "https://play.google.com/store/apps/details?id=com.example.app" --max 500
    uv run python tools/play_store.py com.example.app --max 500 --country us --lang en --info

Flags:
    --max      Max reviews to fetch (default: 500)
    --country  Two-letter country code (default: in)
    --lang     Language code (default: en)
    --info     Also fetch app metadata (rating, installs, description, etc.)
    --out      Output directory (default: data/play_store)
"""
import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from google_play_scraper import Sort, app, reviews


# ── Helpers ───────────────────────────────────────────────────────────────────

def extract_package_id(url_or_id: str) -> str:
    if url_or_id.startswith("http"):
        parsed = urlparse(url_or_id)
        qs = parse_qs(parsed.query)
        if "id" not in qs:
            raise ValueError(f"No ?id= in URL: {url_or_id}")
        return qs["id"][0]
    return url_or_id


# ── App info ──────────────────────────────────────────────────────────────────

def fetch_app_info(package_id: str, country: str = "in", lang: str = "en") -> dict:
    print(f"\n📦 Fetching app info for: {package_id}")
    try:
        info = app(package_id, lang=lang, country=country)
        result = {
            "package_id": package_id,
            "title": info.get("title"),
            "developer": info.get("developer"),
            "score": info.get("score"),
            "ratings": info.get("ratings"),
            "installs": info.get("realInstalls"),
            "installs_text": info.get("installs"),
            "price": info.get("price"),
            "free": info.get("free"),
            "in_app_purchases": info.get("inAppProductPrice"),
            "category": info.get("genre"),
            "released": info.get("released"),
            "last_updated": info.get("updated"),
            "version": info.get("version"),
            "description": (info.get("description") or "")[:1000],
            "summary": info.get("summary"),
            "content_rating": info.get("contentRating"),
            "url": info.get("url"),
        }
        print(f"  ✅ {result['title']} | {result['score']}★ | {result['installs_text']} installs | {result['category']}")
        return result
    except Exception as e:
        print(f"  ❌ Could not fetch app info: {e}")
        return {"package_id": package_id, "error": str(e)}


# ── Reviews ───────────────────────────────────────────────────────────────────

def fetch_reviews(package_id: str, max_reviews: int = 500, country: str = "in", lang: str = "en") -> list:
    print(f"\n💬 Fetching reviews for: {package_id}")
    print(f"   Country: {country} | Language: {lang} | Max: {max_reviews}")

    all_reviews = []
    token = None

    while len(all_reviews) < max_reviews:
        remaining = max_reviews - len(all_reviews)
        try:
            batch, token = reviews(
                package_id,
                lang=lang,
                country=country,
                sort=Sort.NEWEST,
                count=min(200, remaining),
                continuation_token=token,
            )
        except Exception as e:
            print(f"  ⚠️  Batch error: {e}")
            break

        if not batch:
            print("  No more reviews available.")
            break

        all_reviews.extend(batch)
        print(f"  Fetched {len(all_reviews)}...", end="\r", flush=True)

        if token is None:
            break
        time.sleep(0.5)

    print(f"\n  ✅ {len(all_reviews)} reviews fetched")
    return all_reviews


def _clean_review(r: dict) -> dict:
    return {
        "review_id":   r.get("reviewId"),
        "user_name":   r.get("userName"),
        "rating":      r.get("score"),
        "date":        r.get("at").isoformat() if r.get("at") else None,
        "review_text": r.get("content"),
        "thumbs_up":   r.get("thumbsUpCount", 0),
        "app_version": r.get("appVersion"),
        "reply_text":  r.get("replyContent"),
        "reply_date":  r.get("repliedAt").isoformat() if r.get("repliedAt") else None,
    }


# ── Save ──────────────────────────────────────────────────────────────────────

def save(package_id: str, raw_reviews: list, app_info: dict, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    clean = [_clean_review(r) for r in raw_reviews]

    # JSON
    payload = {
        "package_id":  package_id,
        "scraped_at":  datetime.now().isoformat(),
        "app_info":    app_info,
        "total_reviews": len(clean),
        "reviews":     clean,
    }
    json_path = output_dir / "reviews.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"  JSON → {json_path}")

    # CSV
    if clean:
        csv_path = output_dir / "reviews.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(clean[0].keys()))
            writer.writeheader()
            writer.writerows(clean)
        print(f"  CSV  → {csv_path}")

    # Stats
    ratings = [r["rating"] for r in clean if r["rating"]]
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
    parser = argparse.ArgumentParser(description="Google Play Store review scraper")
    parser.add_argument("app", help="Play Store URL or package ID")
    parser.add_argument("--max",     type=int, default=500)
    parser.add_argument("--country", default="in")
    parser.add_argument("--lang",    default="en")
    parser.add_argument("--info",    action="store_true", help="Also fetch app metadata")
    parser.add_argument("--out",     default="data/play_store", help="Output base directory")
    args = parser.parse_args()

    try:
        package_id = extract_package_id(args.app)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    app_info = fetch_app_info(package_id, args.country, args.lang) if args.info else {}
    raw = fetch_reviews(package_id, args.max, args.country, args.lang)

    if not raw:
        print("No reviews fetched.")
        sys.exit(1)

    output_dir = Path(args.out) / package_id
    save(package_id, raw, app_info, output_dir)
    print(f"\n✅ Done → {output_dir}/")


if __name__ == "__main__":
    main()
