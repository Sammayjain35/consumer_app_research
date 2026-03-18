"""
YouTube Research Tool
Fetches channel stats, top videos, and search results using YouTube Data API v3.

Usage:
    uv run python tools/youtube.py --channel "@ChannelHandle" --max-videos 50
    uv run python tools/youtube.py --channel-id UCxxxxxxxx --max-videos 50
    uv run python tools/youtube.py --search "ramayan short videos hindi" --max 20
    uv run python tools/youtube.py --video-id dQw4w9WgXcQ

Requires:
    YOUTUBE_API_KEY in .env
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

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


# ── Channel ───────────────────────────────────────────────────────────────────

def resolve_channel(handle_or_id: str) -> dict:
    """Resolve @handle or channel ID to channel data."""
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
        "channel_id":        ch["id"],
        "title":             ch["snippet"]["title"],
        "description":       ch["snippet"].get("description", "")[:500],
        "country":           ch["snippet"].get("country"),
        "published_at":      ch["snippet"].get("publishedAt"),
        "subscribers":       stats.get("subscriberCount"),
        "total_views":       stats.get("viewCount"),
        "video_count":       stats.get("videoCount"),
        "uploads_playlist":  ch.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads"),
        "url":               f"https://youtube.com/channel/{ch['id']}",
    }
    print(f"\n📺 {result['title']}")
    print(f"   Subscribers: {int(result['subscribers'] or 0):,} | Videos: {result['video_count']} | Views: {int(result['total_views'] or 0):,}")
    return result


def fetch_channel_videos(uploads_playlist: str, max_videos: int = 50) -> list:
    """Fetch recent videos from uploads playlist."""
    print(f"\n🎬 Fetching up to {max_videos} videos...", flush=True)
    videos = []
    next_token = None

    while len(videos) < max_videos:
        params = {
            "part": "snippet,contentDetails",
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
            vid_id = item["contentDetails"]["videoId"]
            snip   = item["snippet"]
            stats  = stats_map.get(vid_id, {}).get("statistics", {})
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
    """Search YouTube for videos matching a query."""
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

    video_ids = [i["id"]["videoId"] for i in items]
    stats_data = _api("videos", {"part": "statistics,contentDetails", "id": ",".join(video_ids)})
    stats_map  = {v["id"]: v for v in stats_data.get("items", [])}

    results = []
    for item in items:
        vid_id = item["id"]["videoId"]
        snip   = item["snippet"]
        stats  = stats_map.get(vid_id, {}).get("statistics", {})
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
        print(f"  {int(stats.get('viewCount', 0)):>10,} views | {snip.get('channelTitle', '')[:25]:<25} | {snip.get('title', '')[:60]}")

    return results


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
    parser.add_argument("--out",        default="data/youtube")
    args = parser.parse_args()

    out = Path(args.out)

    if args.search:
        results = search_videos(args.search, args.max, args.order)
        safe = args.search.replace(" ", "_")[:40]
        save(f"search_{safe}", {"query": args.search, "results": results, "fetched_at": datetime.now().isoformat()}, out)

    elif args.channel or args.channel_id:
        handle = args.channel or args.channel_id
        channel = resolve_channel(handle)
        if not channel:
            sys.exit(1)
        videos = []
        if channel.get("uploads_playlist"):
            videos = fetch_channel_videos(channel["uploads_playlist"], args.max_videos)
        safe = (channel.get("title") or handle).replace(" ", "_")[:40]
        save(safe, {"channel": channel, "videos": videos, "fetched_at": datetime.now().isoformat()}, out)

    elif args.video_id:
        data = _api("videos", {"part": "snippet,statistics,contentDetails", "id": args.video_id})
        save(args.video_id, data, out)


if __name__ == "__main__":
    main()
