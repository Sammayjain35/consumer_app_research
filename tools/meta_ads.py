"""
Meta Ads Library Scraper
Scrapes video ads from Facebook Ads Library + Gemini analysis.

Usage (single brand):
    uv run python tools/meta_ads.py --page-id 158614484189541 --name KiwiCo --max 15

Usage (config file):
    uv run python tools/meta_ads.py --config configs/brands.json

Config JSON format:
    {
      "config": {"default_max_ads_per_competitor": 15, "output_directory": "data/meta_ads"},
      "competitors": [
        {"name": "BrandName", "page_id": "123456", "category": "stem_toys",
         "url": "https://www.facebook.com/ads/library/?...&view_all_page_id=123456"}
      ]
    }
"""
import argparse
import json
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

BASE_URL = (
    "https://www.facebook.com/ads/library/"
    "?active_status=active&ad_type=all&country=ALL"
    "&is_targeted_country=false&media_type=all&search_type=page"
    "&sort_data[direction]=desc&sort_data[mode]=total_impressions"
    "&view_all_page_id={page_id}"
)


# ── Scrape ────────────────────────────────────────────────────────────────────

def _scrape(url: str, max_ads: int, name: str) -> dict:
    ads_data = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})

        def handle_response(response):
            try:
                if "graphql" in response.url and response.status == 200:
                    data = response.json()
                    edges = (
                        data.get("data", {})
                        .get("ad_library_main", {})
                        .get("search_results_connection", {})
                        .get("edges", [])
                    )
                    for edge in edges:
                        for result in edge.get("node", {}).get("collated_results", []):
                            snapshot = result.get("snapshot", {})
                            start_ts = result.get("start_date")
                            started = None
                            if start_ts:
                                try:
                                    started = datetime.fromtimestamp(int(start_ts)).strftime("%d %b %Y")
                                except Exception:
                                    pass
                            meta = {
                                "advertiser": {"name": result.get("page_name") or snapshot.get("page_name", "")},
                                "ad_details": {
                                    "started_running": started,
                                    "publisher_platforms": result.get("publisher_platform", []),
                                },
                                "performance": {
                                    "impressions": result.get("impressions_with_index", {}).get("impressions_text"),
                                    "spend": result.get("spend"),
                                    "currency": result.get("currency"),
                                },
                            }
                            for v in snapshot.get("videos", []):
                                vurl = v.get("video_hd_url") or v.get("video_sd_url")
                                if vurl:
                                    ads_data[vurl] = meta
                            for card in snapshot.get("cards", []):
                                vurl = card.get("video_sd_url") or card.get("video_hd_url")
                                if vurl:
                                    ads_data[vurl] = meta
            except Exception:
                pass

        page.on("response", handle_response)
        print(f"  📡 Loading {name}... (15-30s)", flush=True)
        t0 = datetime.now()
        page.goto(url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)
        for _ in range(5):
            page.evaluate("window.scrollBy(0, 600)")
            page.wait_for_timeout(800)
        elapsed = (datetime.now() - t0).total_seconds()
        print(f"  ✅ Page ready in {elapsed:.1f}s — {len(ads_data)} video ads found", flush=True)
        browser.close()

    return ads_data


# ── Download ──────────────────────────────────────────────────────────────────

def _download(video_url: str, idx: int, ads_data: dict, name: str, tmp_dir: Path):
    meta = ads_data.get(video_url, {"advertiser": {}, "ad_details": {}, "performance": {}})
    video_path = tmp_dir / f"ad_{idx:03d}.mp4"
    json_path  = tmp_dir / f"ad_{idx:03d}.json"
    try:
        r = requests.get(video_url, timeout=30)
        if r.status_code == 200:
            video_path.write_bytes(r.content)
            size_mb = video_path.stat().st_size / (1024 * 1024)
            data = {
                "scraped_at": datetime.now().isoformat(),
                "competitor": name,
                "video": {"filename": video_path.name, "path": str(video_path), "size_mb": round(size_mb, 2)},
                **meta,
            }
            json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            return data
    except Exception as e:
        print(f"  ❌ ad_{idx:03d}: {e}", flush=True)
    return None


# ── Gemini analysis ───────────────────────────────────────────────────────────

def _analyze(video_path: Path, json_path: Path) -> bool:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key or api_key == "your_gemini_api_key_here":
        return False
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        video_data = video_path.read_bytes()
        prompt = """Act as a Performance Marketing Expert analyzing this video ad.

**1. Hook:** Opening message/trigger to stop scroll (keep native Hindi/Hinglish phrases as-is)
**2. Story:** Complete narrative and messaging flow
**3. Visual Style:** What they show and how (animation, live-action, screenshots, text overlays)
**4. Target Audience:** Who is this for? Pain points addressed?
**5. Why It Works:** Psychological/behavioral triggers used
**6. Full Script:** Complete transcript in native language (Hindi/Hinglish) exactly as spoken

Language: Write 1-5 in English, keep native phrases intact, write script (6) in native language."""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(data=video_data, mime_type="video/mp4"),
                prompt,
            ],
        )
        meta = json.loads(json_path.read_text())
        meta["analysis"] = {"raw_response": response.text, "analyzed_at": datetime.now().isoformat()}
        json_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
        return True
    except Exception as e:
        print(f"  ❌ Gemini: {e}", flush=True)
        return False


# ── Run one competitor ────────────────────────────────────────────────────────

def run_competitor(name: str, page_id: str, url: str, max_ads: int, output_base: Path):
    print(f"\n{'='*55}")
    print(f"  {name.upper()}")
    print(f"{'='*55}")

    comp_dir = output_base / name
    comp_dir.mkdir(parents=True, exist_ok=True)

    ads_data = _scrape(url, max_ads, name)
    if not ads_data:
        print(f"  ⚠️  No video ads found for {name}")
        return {"competitor": name, "page_id": page_id, "ads_downloaded": 0}

    video_list = list(ads_data.keys())[:max_ads]
    print(f"\n  [2/3] Downloading {len(video_list)} videos...", flush=True)

    downloaded = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(_download, url, i, ads_data, name, comp_dir): i
                   for i, url in enumerate(video_list, 1)}
        for f in as_completed(futures):
            r = f.result()
            if r:
                downloaded.append(r)

    print(f"\n  [3/3] Gemini analysis ({len(downloaded)} videos)...", flush=True)
    analyzed = 0
    for i in range(1, len(downloaded) + 1):
        vp = comp_dir / f"ad_{i:03d}.mp4"
        jp = comp_dir / f"ad_{i:03d}.json"
        if vp.exists() and jp.exists():
            print(f"    [{i:02d}/{len(downloaded):02d}] analysing...", end=" ", flush=True)
            if _analyze(vp, jp):
                print("✅", flush=True)
                analyzed += 1
            else:
                print("⏭️  skipped", flush=True)

    print(f"\n  ✅ {len(downloaded)} downloaded, {analyzed} analyzed — {comp_dir}/")
    return {"competitor": name, "page_id": page_id, "ads_downloaded": len(downloaded), "directory": str(comp_dir)}


# ── Config mode ───────────────────────────────────────────────────────────────

def run_config(config_file: str):
    with open(config_file) as f:
        config = json.load(f)

    competitors = config["competitors"]
    max_ads     = config["config"]["default_max_ads_per_competitor"]
    output_base = Path(config["config"].get("output_directory", "data/meta_ads"))
    output_base.mkdir(parents=True, exist_ok=True)

    print(f"🎯 {len(competitors)} competitors | {max_ads} ads each")
    print(f"📁 Output: {output_base}/\n")

    results = []
    for idx, c in enumerate(competitors, 1):
        url = c.get("url") or BASE_URL.format(page_id=c["page_id"])
        res = run_competitor(c["name"], c["page_id"], url, max_ads, output_base)
        results.append(res)
        if idx < len(competitors):
            print("  ⏸️  5s pause...", flush=True)
            time.sleep(5)

    summary = {
        "scraping_date": datetime.now().isoformat(),
        "total_competitors": len(competitors),
        "total_ads": sum(r["ads_downloaded"] for r in results),
        "competitors": results,
    }
    summary_path = output_base / "scraping_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    print(f"\n✅ Done — {summary['total_ads']} ads total. Summary: {summary_path}")
    return summary


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Meta Ads Library scraper + Gemini analysis")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--config", help="Path to JSON config file")
    group.add_argument("--page-id", help="Single Facebook page ID")
    parser.add_argument("--name",    default="Brand",  help="Brand name (used with --page-id)")
    parser.add_argument("--max",     type=int, default=15, help="Max ads to scrape (default: 15)")
    parser.add_argument("--out",     default="data/meta_ads", help="Output directory")
    args = parser.parse_args()

    if args.config:
        run_config(args.config)
    else:
        url = BASE_URL.format(page_id=args.page_id)
        run_competitor(args.name, args.page_id, url, args.max, Path(args.out))


if __name__ == "__main__":
    main()
