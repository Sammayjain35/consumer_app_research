"""
YouTube Research Tool
Fetches channel stats, top videos, search results, transcripts, and Gemini analysis.

Usage:
    uv run python tools/youtube.py --channel "@ChannelHandle" --max-videos 50
    uv run python tools/youtube.py --channel-id UCxxxxxxxx --max-videos 50
    uv run python tools/youtube.py --search "fantasy cricket tips india" --max 20
    uv run python tools/youtube.py --video-id dQw4w9WgXcQ
    uv run python tools/youtube.py --search "IPL tips" --max 10 --transcript
    uv run python tools/youtube.py --search "IPL tips" --max 10 --transcript --analyze

Flags:
    --transcript   Fetch transcript for each video (no API key needed)
    --analyze      Send each transcript to Gemini for AI analysis (requires GEMINI_API_KEY)

Requires:
    YOUTUBE_API_KEY in .env
    GEMINI_API_KEY in .env (only for --analyze)
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound

load_dotenv()

BASE = "https://www.googleapis.com/youtube/v3"


def _api(endpoint: str, params: dict) -> dict:
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key or api_key == "your_youtube_api_key_here":
        print("❌ YOUTUBE_API_KEY not set in .env", file=sys.stderr)
        sys.exit(1)
    params["key"] = api_key
    r = requests.get(f"{BASE}/{endpoint}", params=params, timeout=15)
    r.raise_for_status()
    return r.json()


# ── Transcript ────────────────────────────────────────────────────────────────

def fetch_transcript(video_id: str) -> dict:
    """Fetch transcript for a video. Returns {text, language, segments}."""
    try:
        api = YouTubeTranscriptApi()
        # Try English first, then fall back to any available language
        try:
            transcript = api.fetch(video_id, languages=["en", "en-IN"])
            language = "en"
        except NoTranscriptFound:
            transcript_list = api.list(video_id)
            transcript = transcript_list.find_generated_transcript(
                [t.language_code for t in transcript_list]
            ).fetch()
            language = transcript.language_code if hasattr(transcript, "language_code") else "unknown"

        segments  = [{"text": s.text, "start": s.start, "duration": s.duration} for s in transcript]
        full_text = " ".join(s["text"] for s in segments)
        return {
            "available":  True,
            "language":   language,
            "text":       full_text,
            "segments":   segments,
            "word_count": len(full_text.split()),
        }
    except TranscriptsDisabled:
        return {"available": False, "reason": "Transcripts disabled for this video"}
    except Exception as e:
        return {"available": False, "reason": str(e)}


# ── Gemini Analysis ───────────────────────────────────────────────────────────

def analyze_transcript(video_title: str, transcript_text: str) -> str:
    """Send transcript to Gemini for analysis."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "GEMINI_API_KEY not set"

    try:
        from google import genai
        client = genai.Client(api_key=api_key)

        prompt = f"""You are a content research analyst. Analyze this YouTube video transcript.

Video Title: {video_title}

Transcript:
{transcript_text[:8000]}

Provide analysis in this structure:

**1. Core Topic**
What is this video actually about in one sentence?

**2. Key Points**
The 5 most important things covered (bullet points).

**3. Hook**
How does the video open? What keeps viewers watching?

**4. Target Audience**
Who is this for? What problem does it solve for them?

**5. Sentiment & Tone**
Is it educational, entertaining, promotional, controversial? Overall tone?

**6. Quotable Moments**
2-3 most impactful lines or statements from the transcript (quote directly).
"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[prompt],
        )
        return response.text
    except Exception as e:
        return f"Analysis failed: {e}"


# ── Channel ───────────────────────────────────────────────────────────────────

def resolve_channel(handle_or_id: str) -> dict:
    if handle_or_id.startswith("UC"):
        data = _api("channels", {"part": "snippet,statistics,contentDetails", "id": handle_or_id})
    else:
        handle = handle_or_id.lstrip("@")
        data = _api("channels", {"part": "snippet,statistics,contentDetails", "forHandle": handle})

    items = data.get("items", [])
    if not items:
        print(f"❌ Channel not found: {handle_or_id}")
        return {}
    ch = items[0]
    stats = ch.get("statistics", {})
    result = {
        "channel_id":       ch["id"],
        "title":            ch["snippet"]["title"],
        "description":      ch["snippet"].get("description", "")[:500],
        "country":          ch["snippet"].get("country"),
        "published_at":     ch["snippet"].get("publishedAt"),
        "subscribers":      stats.get("subscriberCount"),
        "total_views":      stats.get("viewCount"),
        "video_count":      stats.get("videoCount"),
        "uploads_playlist": ch.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads"),
        "url":              f"https://youtube.com/channel/{ch['id']}",
    }
    print(f"\n📺 {result['title']}")
    print(f"   Subscribers: {int(result['subscribers'] or 0):,} | Videos: {result['video_count']} | Views: {int(result['total_views'] or 0):,}")
    return result


def fetch_channel_videos(uploads_playlist: str, max_videos: int = 50) -> list:
    print(f"\n🎬 Fetching up to {max_videos} videos...", flush=True)
    videos = []
    next_token = None

    while len(videos) < max_videos:
        params = {
            "part":       "snippet,contentDetails",
            "playlistId": uploads_playlist,
            "maxResults": min(50, max_videos - len(videos)),
        }
        if next_token:
            params["pageToken"] = next_token

        data = _api("playlistItems", params)
        items = data.get("items", [])
        if not items:
            break

        video_ids = [i["contentDetails"]["videoId"] for i in items]
        stats_data = _api("videos", {"part": "statistics,contentDetails", "id": ",".join(video_ids)})
        stats_map = {v["id"]: v for v in stats_data.get("items", [])}

        for item in items:
            vid_id   = item["contentDetails"]["videoId"]
            snip     = item["snippet"]
            stats    = stats_map.get(vid_id, {}).get("statistics", {})
            duration = stats_map.get(vid_id, {}).get("contentDetails", {}).get("duration", "")
            videos.append({
                "video_id":     vid_id,
                "title":        snip.get("title"),
                "published_at": snip.get("publishedAt"),
                "description":  (snip.get("description") or "")[:300],
                "thumbnail":    snip.get("thumbnails", {}).get("high", {}).get("url"),
                "duration":     duration,
                "views":        int(stats.get("viewCount", 0)),
                "likes":        int(stats.get("likeCount", 0)),
                "comments":     int(stats.get("commentCount", 0)),
                "url":          f"https://youtube.com/watch?v={vid_id}",
            })

        print(f"  Fetched {len(videos)} videos...", end="\r", flush=True)
        next_token = data.get("nextPageToken")
        if not next_token:
            break

    videos.sort(key=lambda v: v["views"], reverse=True)
    print(f"\n  ✅ {len(videos)} videos fetched (sorted by views)")
    return videos


# ── Search ────────────────────────────────────────────────────────────────────

def search_videos(query: str, max_results: int = 20, order: str = "viewCount") -> list:
    print(f"\n🔍 Searching YouTube: '{query}' (order={order})")
    params = {
        "part":       "snippet",
        "q":          query,
        "type":       "video",
        "maxResults": min(max_results, 50),
        "order":      order,
    }
    data = _api("search", params)
    items = data.get("items", [])
    if not items:
        return []

    video_ids  = [i["id"]["videoId"] for i in items]
    stats_data = _api("videos", {"part": "statistics,contentDetails", "id": ",".join(video_ids)})
    stats_map  = {v["id"]: v for v in stats_data.get("items", [])}

    results = []
    for item in items:
        vid_id   = item["id"]["videoId"]
        snip     = item["snippet"]
        stats    = stats_map.get(vid_id, {}).get("statistics", {})
        duration = stats_map.get(vid_id, {}).get("contentDetails", {}).get("duration", "")
        results.append({
            "video_id":     vid_id,
            "title":        snip.get("title"),
            "channel":      snip.get("channelTitle"),
            "channel_id":   snip.get("channelId"),
            "published_at": snip.get("publishedAt"),
            "description":  (snip.get("description") or "")[:300],
            "duration":     duration,
            "views":        int(stats.get("viewCount", 0)),
            "likes":        int(stats.get("likeCount", 0)),
            "comments":     int(stats.get("commentCount", 0)),
            "url":          f"https://youtube.com/watch?v={vid_id}",
        })
        print(f"  {int(stats.get('viewCount', 0)):>10,} views | {snip.get('channelTitle', '')[:25]:<25} | {snip.get('title', '')[:55]}")

    return results


# ── Enrich with transcripts + analysis ───────────────────────────────────────

def enrich_videos(videos: list, do_transcript: bool, do_analyze: bool) -> list:
    if not do_transcript:
        return videos

    print(f"\n📝 Fetching transcripts for {len(videos)} videos...")
    for i, video in enumerate(videos, 1):
        vid_id = video["video_id"]
        title  = video.get("title", "")
        print(f"  [{i:02d}/{len(videos):02d}] {title[:55]}...", end=" ", flush=True)

        transcript = fetch_transcript(vid_id)
        video["transcript"] = transcript

        if transcript["available"]:
            print(f"✅ {transcript['word_count']} words ({transcript['language']})", end="")
            if do_analyze:
                print(" → analyzing...", end=" ", flush=True)
                video["analysis"] = analyze_transcript(title, transcript["text"])
                print("✅")
            else:
                print()
        else:
            print(f"⚠️  {transcript['reason']}")

    return videos


# ── Save ──────────────────────────────────────────────────────────────────────

def save(name: str, data: dict, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{name}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    print(f"\n✅ Saved → {path}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="YouTube research tool")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--channel",    help="@handle or channel URL")
    group.add_argument("--channel-id", help="Channel ID (UCxxxxxxxx)")
    group.add_argument("--search",     help="Search query")
    group.add_argument("--video-id",   help="Single video ID for stats")
    parser.add_argument("--max-videos", type=int, default=50)
    parser.add_argument("--max",        type=int, default=20, help="Max search results")
    parser.add_argument("--order",      default="viewCount", choices=["viewCount", "relevance", "date"])
    parser.add_argument("--transcript", action="store_true", help="Fetch transcript for each video")
    parser.add_argument("--analyze",    action="store_true", help="Analyze each transcript with Gemini")
    parser.add_argument("--out",        default="data/youtube")
    args = parser.parse_args()

    # --analyze implies --transcript
    if args.analyze:
        args.transcript = True

    out = Path(args.out)

    if args.search:
        videos = search_videos(args.search, args.max, args.order)
        videos = enrich_videos(videos, args.transcript, args.analyze)
        safe   = args.search.replace(" ", "_")[:40]
        save(f"search_{safe}", {
            "query":      args.search,
            "fetched_at": datetime.now().isoformat(),
            "results":    videos,
        }, out)

    elif args.channel or args.channel_id:
        handle  = args.channel or args.channel_id
        channel = resolve_channel(handle)
        if not channel:
            sys.exit(1)
        videos = []
        if channel.get("uploads_playlist"):
            videos = fetch_channel_videos(channel["uploads_playlist"], args.max_videos)
        videos = enrich_videos(videos, args.transcript, args.analyze)
        safe   = (channel.get("title") or handle).replace(" ", "_")[:40]
        save(safe, {
            "channel":    channel,
            "videos":     videos,
            "fetched_at": datetime.now().isoformat(),
        }, out)

    elif args.video_id:
        data = _api("videos", {"part": "snippet,statistics,contentDetails", "id": args.video_id})
        items = data.get("items", [])
        if items and args.transcript:
            video = {
                "video_id": args.video_id,
                "title":    items[0].get("snippet", {}).get("title", ""),
            }
            video = enrich_videos([video], args.transcript, args.analyze)[0]
            data["transcript"] = video.get("transcript")
            data["analysis"]   = video.get("analysis")
        save(args.video_id, data, out)


if __name__ == "__main__":
    main()
