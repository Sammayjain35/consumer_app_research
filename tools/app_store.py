"""
iOS App Store Review Scraper
Uses the public iTunes RSS + Search API (no API key required).

Usage:
    uv run python tools/app_store.py --app-id 1234567890 --max 500
    uv run python tools/app_store.py --search "ramayan" --country in --max 10
    uv run python tools/app_store.py --app-id 1234567890 --info

Flags:
    --app-id   iTunes numeric app ID
    --search   Search App Store by keyword (returns app IDs)
    --country  Two-letter country code (default: in)
    --max      Max reviews to fetch (default: 200)
    --info     Fetch app metadata
    --out      Output directory (default: data/app_store)
"""
import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

SEARCH_URL = "https://itunes.apple.com/search"
LOOKUP_URL = "https://itunes.apple.com/lookup"
RSS_URL    = "https://itunes.apple.com/{country}/rss/customerreviews/page={page}/id={app_id}/sortby=mostrecent/json"


# ── App search ────────────────────────────────────────────────────────────────

def search_apps(query: str, country: str = "in", limit: int = 10) -> list:
    print(f"\n🔍 Searching App Store: '{query}' (country={country})")
    params = {"term": query, "country": country, "media": "software", "limit": limit}
    r = requests.get(SEARCH_URL, params=params, timeout=15)
    r.raise_for_status()
    results = r.json().get("results", [])
    apps = []
    for a in results:
        apps.append({
            "app_id":       a.get("trackId"),
            "name":         a.get("trackName"),
            "developer":    a.get("artistName"),
            "price":        a.get("price"),
            "rating":       a.get("averageUserRating"),
            "rating_count": a.get("userRatingCount"),
            "category":     a.get("primaryGenreName"),
            "url":          a.get("trackViewUrl"),
            "description":  (a.get("description") or "")[:500],
        })
        print(f"  {a.get('trackId')} | {a.get('trackName')} | {a.get('averageUserRating')}★ | {a.get('userRatingCount')} ratings")
    return apps


# ── App info ──────────────────────────────────────────────────────────────────

def fetch_app_info(app_id: str, country: str = "in") -> dict:
    print(f"\n📦 App info for: {app_id}")
    r = requests.get(LOOKUP_URL, params={"id": app_id, "country": country}, timeout=15)
    r.raise_for_status()
    results = r.json().get("results", [])
    if not results:
        return {"app_id": app_id, "error": "Not found"}
    a = results[0]
    info = {
        "app_id":         app_id,
        "name":           a.get("trackName"),
        "developer":      a.get("artistName"),
        "price":          a.get("price"),
        "free":           a.get("price") == 0,
        "rating":         a.get("averageUserRating"),
        "rating_count":   a.get("userRatingCount"),
        "category":       a.get("primaryGenreName"),
        "content_rating": a.get("contentAdvisoryRating"),
        "version":        a.get("version"),
        "released":       a.get("releaseDate"),
        "updated":        a.get("currentVersionReleaseDate"),
        "description":    (a.get("description") or "")[:1000],
        "url":            a.get("trackViewUrl"),
    }
    print(f"  ✅ {info['name']} | {info['rating']}★ ({info['rating_count']}) | {info['category']}")
    return info


# ── Reviews ───────────────────────────────────────────────────────────────────

def fetch_reviews(app_id: str, country: str = "in", max_reviews: int = 200) -> list:
    print(f"\n💬 Fetching iOS reviews for app {app_id} (country={country})")
    all_reviews = []

    for page in range(1, 11):  # max 10 pages × ~50 reviews = 500
        if len(all_reviews) >= max_reviews:
            break
        url = RSS_URL.format(country=country, page=page, app_id=app_id)
        try:
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            data = r.json()
            entries = data.get("feed", {}).get("entry", [])
            if not entries or (isinstance(entries, dict)):
                # Single entry or none
                break
            for entry in entries:
                if isinstance(entry, dict) and "im:rating" in entry:
                    all_reviews.append({
                        "review_id":   entry.get("id", {}).get("label"),
                        "user_name":   entry.get("author", {}).get("name", {}).get("label"),
                        "rating":      int(entry.get("im:rating", {}).get("label", 0)),
                        "title":       entry.get("title", {}).get("label"),
                        "review_text": entry.get("content", {}).get("label"),
                        "version":     entry.get("im:version", {}).get("label"),
                        "date":        entry.get("updated", {}).get("label"),
                        "vote_count":  entry.get("im:voteCount", {}).get("label"),
                    })
            print(f"  Page {page}: {len(all_reviews)} reviews so far...", end="\r", flush=True)
            time.sleep(0.3)
        except Exception as e:
            print(f"\n  ⚠️  Page {page} error: {e}")
            break

    all_reviews = all_reviews[:max_reviews]
    print(f"\n  ✅ {len(all_reviews)} iOS reviews fetched")
    return all_reviews


# ── Save ──────────────────────────────────────────────────────────────────────

def save(app_id: str, reviews_data: list, app_info: dict, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "app_id":        app_id,
        "scraped_at":    datetime.now().isoformat(),
        "app_info":      app_info,
        "total_reviews": len(reviews_data),
        "reviews":       reviews_data,
    }
    json_path = output_dir / "reviews.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"  JSON → {json_path}")

    if reviews_data:
        csv_path = output_dir / "reviews.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(reviews_data[0].keys()))
            writer.writeheader()
            writer.writerows(reviews_data)
        print(f"  CSV  → {csv_path}")

    ratings = [r["rating"] for r in reviews_data if r.get("rating")]
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
    parser = argparse.ArgumentParser(description="iOS App Store review scraper")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--app-id", help="iTunes numeric app ID")
    group.add_argument("--search", help="Search keyword to find apps")
    parser.add_argument("--country", default="in")
    parser.add_argument("--max",     type=int, default=200)
    parser.add_argument("--info",    action="store_true")
    parser.add_argument("--out",     default="data/app_store")
    args = parser.parse_args()

    if args.search:
        results = search_apps(args.search, args.country, limit=args.max)
        out = Path(args.out) / "search_results"
        out.mkdir(parents=True, exist_ok=True)
        (out / "results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False))
        print(f"\n✅ {len(results)} apps found → {out}/results.json")
        return

    app_info = fetch_app_info(args.app_id, args.country) if args.info else {}
    rev = fetch_reviews(args.app_id, args.country, args.max)

    out = Path(args.out) / str(args.app_id)
    save(args.app_id, rev, app_info, out)
    print(f"\n✅ Done → {out}/")


if __name__ == "__main__":
    main()
