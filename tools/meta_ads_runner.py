"""
Production scraper - Scrapes multiple competitors and organizes for Gemini analysis
"""
import json
import os
import time
from pathlib import Path
from meta_ads_scraper import scrape_ads
import shutil
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load environment variables
load_dotenv()


VIDEO_PROMPT = """Act as a Performance Marketing Expert analyzing this video ad.

Analyze this ad and provide insights in the following structure:

**1. Hook:**
What is the opening message/trigger used to stop the scroll? (Keep native Hindi/Hinglish phrases as-is)

**2. Story:**
What is the complete narrative and messaging flow of the ad?

**3. Visual Style:**
What do they show and how do they show it? (Animation, live-action, screenshots, text overlays, etc.)

**4. Target Audience:**
Who is this ad for? What pain points are being addressed?

**5. Why It Works:**
What makes this creative effective? What psychological or behavioral triggers are being used?

**6. Full Script:**
Provide the complete transcript of the ad in the native language (Hindi/Hinglish) exactly as spoken in the video.

---

**Language Guidelines:**
- Write analysis (points 1-5) in English
- Keep native phrases (Hindi/Hinglish) in their original language when referencing specific words/hooks
- Write the Full Script (point 6) entirely in native Hindi/Hinglish as used in the ad
"""

IMAGE_PROMPT = """Act as a Performance Marketing Expert analyzing this static image ad.

Analyze this ad and provide insights in the following structure:

**1. Hook:**
What is the headline or primary text used to stop the scroll? Quote it exactly.

**2. Copy & Messaging:**
What is the full ad copy? What is the core message being communicated?

**3. Visual Style:**
Describe the visual design — layout, colors, imagery, text placement, use of faces/products/screenshots.

**4. Target Audience:**
Who is this ad for? What pain points or desires are being addressed?

**5. Why It Works:**
What makes this creative effective? What psychological or behavioral triggers are being used?

**6. CTA & Offer:**
What is the call-to-action? Is there a specific offer, discount, or urgency element?

---

**Language Guidelines:**
- Write analysis in English
- Quote any Hindi/Hinglish copy exactly as it appears in the image
"""


def analyze_ad_with_gemini(media_path: Path, json_path: Path, ad_type: str = "video") -> bool:
    """Analyze a video or image ad with Gemini and add the analysis to its JSON file."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key or api_key == "your_api_key_here":
        print("   ⚠️  Gemini API key not set, skipping analysis")
        return False

    try:
        client = genai.Client(api_key=api_key)

        with open(media_path, "rb") as f:
            media_data = f.read()

        if ad_type == "video":
            mime_type = "video/mp4"
            prompt = VIDEO_PROMPT
        else:
            mime_type = "image/jpeg"
            prompt = IMAGE_PROMPT

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(data=media_data, mime_type=mime_type),
                prompt,
            ],
        )

        with open(json_path) as f:
            metadata = json.load(f)

        metadata["analysis"] = {
            "raw_response": response.text,
            "analyzed_at": datetime.now().isoformat(),
        }

        with open(json_path, "w") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        return True

    except Exception as e:
        print(f"   ❌ Analysis failed: {e}")
        return False


def organize_for_analysis(competitors_file: str = "test_competitors.json"):
    """
    Scrape competitors and organize data for Gemini video analysis

    Creates structure:
    data/
    ├── Crafto/
    │   ├── ad_001.mp4, ad_001.json
    │   ├── ad_002.mp4, ad_002.json
    │   └── ...
    ├── Seekho/
    │   └── ...
    └── scraping_summary.json
    """

    # Load config
    print("📋 Loading configuration...\n")
    with open(competitors_file) as f:
        config = json.load(f)

    competitors = config["competitors"]
    max_ads = config["config"]["default_max_ads_per_competitor"]
    output_base = Path(config["config"]["output_directory"])

    total_competitors = len(competitors)
    total_ads_expected = total_competitors * max_ads

    print(f"🎯 {total_competitors} competitors  |  {max_ads} ads each  |  {total_ads_expected} total ads")
    print(f"📁 Output: {output_base}/")
    print(f"🕐 Started: {datetime.now().strftime('%H:%M:%S')}\n")
    print("=" * 60)

    # Create base directory
    output_base.mkdir(exist_ok=True)

    all_results = []
    import time

    # Scrape each competitor
    for idx, competitor in enumerate(competitors, 1):
        name = competitor["name"]
        url = competitor["url"]
        comp_start = datetime.now()

        print(f"\n{'=' * 60}")
        print(f"  COMPETITOR {idx}/{total_competitors}: {name.upper()}")
        print(f"  Time: {comp_start.strftime('%H:%M:%S')}")
        print(f"{'=' * 60}")

        # ── STAGE 1: SCRAPE ──────────────────────────────────────
        print(f"\n[STAGE 1/3] Scraping {name}...", flush=True)
        result = scrape_ads(url, max_ads, name)

        if result:
            competitor_dir = output_base / name
            competitor_dir.mkdir(exist_ok=True)

            source_dir = Path("downloaded_ads")
            media_dir  = source_dir / "media"

            # ── STAGE 2: ORGANISE ─────────────────────────────────
            if media_dir.exists():
                # Collect all media files (videos + images) sorted by name
                media_files = sorted(
                    list(media_dir.glob("*.mp4")) + list(media_dir.glob("*.jpg"))
                )
                print(f"\n[STAGE 2/3] Organising {len(media_files)} files into {competitor_dir}/", flush=True)

                for i, media_file in enumerate(media_files, 1):
                    ext       = media_file.suffix          # .mp4 or .jpg
                    json_file = source_dir / f"{media_file.stem}.json"
                    new_media = competitor_dir / f"ad_{i:03d}{ext}"
                    new_json  = competitor_dir / f"ad_{i:03d}.json"

                    shutil.move(str(media_file), str(new_media))

                    if json_file.exists():
                        with open(json_file) as f:
                            metadata = json.load(f)
                        metadata["media"]["filename"] = new_media.name
                        metadata["media"]["path"]     = str(new_media)
                        metadata["ad_number"]         = i
                        metadata["competitor"]        = name
                        with open(new_json, "w") as f:
                            json.dump(metadata, f, indent=2)
                        json_file.unlink()

                print(f"   ✅ {len(media_files)} files ready")

                # ── STAGE 3: ANALYSE ──────────────────────────────
                print(f"\n[STAGE 3/3] Gemini analysis for {name} ({len(media_files)} ads)...", flush=True)
                analyzed_count = 0
                for i, media_file in enumerate(
                    sorted(list(competitor_dir.glob("ad_*.mp4")) + list(competitor_dir.glob("ad_*.jpg"))),
                    1,
                ):
                    json_path = competitor_dir / f"{media_file.stem}.json"
                    ad_type   = "video" if media_file.suffix == ".mp4" else "image"
                    icon      = "🎬" if ad_type == "video" else "🖼️"
                    t0 = datetime.now()

                    print(f"   [{i:02d}/{len(media_files):02d}] {icon} {name} › {media_file.name}  analysing...", end=" ", flush=True)
                    if analyze_ad_with_gemini(media_file, json_path, ad_type):
                        elapsed = (datetime.now() - t0).total_seconds()
                        print(f"✅  ({elapsed:.1f}s)", flush=True)
                        analyzed_count += 1
                    else:
                        print("⏭️  skipped", flush=True)

                comp_elapsed = (datetime.now() - comp_start).total_seconds()
                print(f"\n   ✅ {analyzed_count}/{len(media_files)} analysed  |  competitor done in {comp_elapsed:.0f}s")

            # Clean up temp dir
            if source_dir.exists():
                shutil.rmtree(source_dir, ignore_errors=True)

            all_results.append({
                "competitor":            name,
                "page_id":               competitor["page_id"],
                "category":              competitor.get("category", ""),
                "ads_downloaded":        result["total_ads"],
                "videos":                result.get("videos", 0),
                "images":                result.get("images", 0),
                "download_time_seconds": result["download_time_seconds"],
                "directory":             str(competitor_dir),
            })

        # Delay between competitors
        if idx < total_competitors:
            print(f"\n⏸️  Waiting 5s before {competitors[idx]['name']}...", flush=True)
            time.sleep(5)

    # Save overall summary
    summary = {
        "scraping_date": datetime.now().isoformat(),
        "total_competitors": len(competitors),
        "total_ads": sum(r["ads_downloaded"] for r in all_results),
        "competitors": all_results
    }

    summary_path = output_base / "scraping_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n{'=' * 60}")
    print(f"✅ SCRAPING COMPLETE")
    print(f"{'=' * 60}")
    print(f"\n📊 Summary:")
    print(f"   Total competitors: {len(competitors)}")
    print(f"   Total ads: {summary['total_ads']}")
    print(f"   Data location: {output_base}/")
    print(f"   Summary: {summary_path}")

    print(f"\n📁 Directory structure:")
    for comp in all_results:
        print(f"   {output_base}/{comp['competitor']}/ - {comp['ads_downloaded']} ads ({comp.get('videos', 0)} videos, {comp.get('images', 0)} images)")

    print(f"\n✅ All ads scraped and analyzed!")

    return summary


if __name__ == "__main__":
    import sys
    config_file = sys.argv[1] if len(sys.argv) > 1 else "test_competitors.json"
    try:
        organize_for_analysis(config_file)
    except KeyboardInterrupt:
        print("\n\n⚠️  Scraping interrupted")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
