"""
Meta Ads Library Scraper — Videos + Images
Intercepts GraphQL API to capture ad media URLs + metadata, then downloads in parallel.
"""
from playwright.sync_api import sync_playwright
import json
import os
from datetime import datetime
from pathlib import Path
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed


def scrape_ads(url: str, max_ads: int = 10, name: str = "Unknown") -> dict | None:
    """
    Scrape Meta Ads Library for both video and image ads.
    Returns summary dict or None if nothing downloaded.
    """
    print(f"\n⚡ META ADS SCRAPER")
    print(f"🎯 Target: {name}")
    print(f"📊 Max ads: {max_ads}\n")

    output_dir = Path("downloaded_ads")
    output_dir.mkdir(exist_ok=True)
    (output_dir / "media").mkdir(exist_ok=True)

    # Map media_url → {metadata, ad_type}
    ads_data: dict[str, dict] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})

        def handle_response(response):
            try:
                if "graphql" not in response.url or response.status != 200:
                    return
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
                        started_running = None
                        if start_ts:
                            try:
                                started_running = datetime.fromtimestamp(int(start_ts)).strftime("%d %b %Y")
                            except Exception:
                                pass

                        metadata = {
                            "advertiser": {
                                "name": result.get("page_name") or snapshot.get("page_name", "")
                            },
                            "ad_details": {
                                "started_running": started_running,
                                "publisher_platforms": result.get("publisher_platform", []),
                                "body": snapshot.get("body", {}).get("text", "") if isinstance(snapshot.get("body"), dict) else snapshot.get("body", ""),
                                "title": snapshot.get("title", ""),
                                "caption": snapshot.get("caption", ""),
                                "cta_text": snapshot.get("cta_text", ""),
                                "link_url": snapshot.get("link_url", ""),
                            },
                            "performance": {
                                "impressions": result.get("impressions_with_index", {}).get("impressions_text"),
                                "spend": result.get("spend"),
                                "currency": result.get("currency"),
                            },
                        }

                        # ── Video ads ─────────────────────────────────
                        for v in snapshot.get("videos", []):
                            media_url = v.get("video_hd_url") or v.get("video_sd_url")
                            if media_url and media_url not in ads_data:
                                ads_data[media_url] = {**metadata, "ad_type": "video"}

                        # ── Image ads ─────────────────────────────────
                        for img in snapshot.get("images", []):
                            media_url = img.get("original_image_url") or img.get("resized_image_url")
                            if media_url and media_url not in ads_data:
                                ads_data[media_url] = {**metadata, "ad_type": "image"}

                        # ── Carousel cards (video or image) ───────────
                        for card in snapshot.get("cards", []):
                            video_url = card.get("video_hd_url") or card.get("video_sd_url")
                            image_url = card.get("original_image_url") or card.get("resized_image_url")
                            if video_url and video_url not in ads_data:
                                ads_data[video_url] = {**metadata, "ad_type": "video"}
                            elif image_url and image_url not in ads_data:
                                ads_data[image_url] = {**metadata, "ad_type": "image"}

            except Exception:
                pass

        page.on("response", handle_response)

        print("📡 Loading page... (15-30s, please wait)", flush=True)
        start = datetime.now()
        page.goto(url, wait_until="networkidle", timeout=60000)
        print(f"   ↳ Page loaded ({(datetime.now() - start).total_seconds():.1f}s), rendering ads...", flush=True)
        page.wait_for_timeout(3000)

        print("   ↳ Scrolling to load more ads...", flush=True)
        for _ in range(5):
            page.evaluate("window.scrollBy(0, 600)")
            page.wait_for_timeout(800)

        elapsed = (datetime.now() - start).total_seconds()
        videos_found = sum(1 for v in ads_data.values() if v["ad_type"] == "video")
        images_found = sum(1 for v in ads_data.values() if v["ad_type"] == "image")
        print(f"✅ Page ready in {elapsed:.1f}s")
        print(f"📊 Found {len(ads_data)} ads from GraphQL: {videos_found} videos, {images_found} images")

        browser.close()

    ad_list = list(ads_data.items())[:max_ads]
    if not ad_list:
        return None

    print(f"\n⬇️  Downloading {len(ad_list)} ads...")
    start_download = datetime.now()

    def download_ad(item, idx):
        media_url, meta = item
        ad_type = meta["ad_type"]
        ext = "mp4" if ad_type == "video" else "jpg"
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{idx:03d}"
            media_file = f"ad_{timestamp}.{ext}"
            json_file  = f"ad_{timestamp}.json"
            media_path = output_dir / "media" / media_file
            json_path  = output_dir / json_file

            response = requests.get(media_url, timeout=30)
            if response.status_code != 200:
                print(f"   ❌ Ad #{idx}: HTTP {response.status_code}")
                return None

            with open(media_path, "wb") as f:
                f.write(response.content)

            size_mb = os.path.getsize(media_path) / (1024 * 1024)

            data = {
                "scraped_at": datetime.now().isoformat(),
                "competitor": name,
                "ad_type": ad_type,
                "media": {
                    "filename": media_file,
                    "path": str(media_path),
                    "size_mb": round(size_mb, 2),
                    "url": media_url,
                },
                **{k: v for k, v in meta.items() if k != "ad_type"},
            }

            with open(json_path, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            adv     = meta.get("advertiser", {}).get("name", "Unknown")[:25]
            started = meta.get("ad_details", {}).get("started_running", "N/A")
            imp     = meta.get("performance", {}).get("impressions", "N/A")
            icon    = "🎬" if ad_type == "video" else "🖼️"
            print(f"   {icon} Ad #{idx}: {adv} | {started} | {imp} | {size_mb:.2f}MB")
            return data

        except Exception as e:
            print(f"   ❌ Ad #{idx}: {str(e)[:50]}")
            return None

    downloaded = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(download_ad, item, i) for i, item in enumerate(ad_list, 1)]
        for future in as_completed(futures):
            result = future.result()
            if result:
                downloaded.append(result)

    download_time = (datetime.now() - start_download).total_seconds()
    vids = sum(1 for d in downloaded if d["ad_type"] == "video")
    imgs = sum(1 for d in downloaded if d["ad_type"] == "image")

    print(f"\n{'=' * 60}")
    print(f"✅ Downloaded {len(downloaded)} ads in {download_time:.1f}s  ({vids} videos, {imgs} images)")
    if downloaded:
        print(f"⚡ Average: {download_time / len(downloaded):.2f}s per ad")
    print(f"{'=' * 60}")

    summary = {
        "total_ads": len(downloaded),
        "videos": vids,
        "images": imgs,
        "competitor": name,
        "scraped_at": datetime.now().isoformat(),
        "download_time_seconds": round(download_time, 2),
        "ads": downloaded,
    }

    with open(output_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    return summary


# Keep old name as alias so nothing else breaks
scrape_videos_ultra_fast = scrape_ads


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: uv run python tools/meta_ads_scraper.py <url> [max_ads] [name]")
        sys.exit(1)

    _url     = sys.argv[1]
    _max_ads = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    _name    = sys.argv[3] if len(sys.argv) > 3 else "Unknown"

    scrape_ads(_url, _max_ads, _name)
