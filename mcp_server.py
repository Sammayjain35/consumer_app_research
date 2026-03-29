"""
Research Agent — MCP Server
Exposes research tools (Reddit, YouTube, Play Store, App Store, Google Trends)
as MCP tools that Claude can call.

Run locally:
    uv run python mcp_server.py

Deploy on Railway:
    railway up
"""
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv()

# So tools/ imports work when running from project root
sys.path.insert(0, str(Path(__file__).parent))

mcp = FastMCP(
    name="Research Agent",
    instructions=(
        "A market research agent with access to Reddit, YouTube, Google Play Store, "
        "iOS App Store, and Google Trends. Use these tools to gather real data about "
        "any topic, brand, or market. Combine multiple tools for comprehensive research."
    ),
)


# ── Reddit ────────────────────────────────────────────────────────────────────

@mcp.tool()
def reddit_search(
    query: str,
    subreddits: str = "",
    max_posts: int = 30,
    sort: str = "relevance",
) -> str:
    """
    Search Reddit for posts about a topic.

    Args:
        query: Search query (e.g. "best budgeting app india")
        subreddits: Optional comma-separated subreddits to scope search (e.g. "india,personalfinance")
        max_posts: Max posts to return (default 30, max 50)
        sort: Sort order — relevance, hot, top, new (default: relevance)
    """
    import praw

    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    if not client_id or not client_secret:
        return json.dumps({"error": "REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET not configured on server"})

    max_posts = min(max_posts, 50)

    reddit = praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent="research-mcp/1.0",
    )

    import re
    IMAGE_RE = re.compile(r"https?://\S+\.(?:png|jpg|jpeg|gif|bmp|svg|webp)", re.IGNORECASE)

    def clean(text: str) -> str:
        if not text:
            return ""
        text = IMAGE_RE.sub("", text)
        return re.sub(r"\s+", " ", text).strip()

    scoped = [s.strip() for s in subreddits.split(",")] if subreddits.strip() else []
    scope = "+".join(scoped) if scoped else "all"
    sub = reddit.subreddit(scope)

    posts = []
    for post in sub.search(query, sort=sort, limit=max_posts):
        posts.append({
            "title":        clean(post.title),
            "text":         clean(post.selftext)[:500],
            "subreddit":    str(post.subreddit),
            "score":        post.score,
            "upvote_ratio": post.upvote_ratio,
            "num_comments": post.num_comments,
            "date":         datetime.utcfromtimestamp(post.created_utc).isoformat(),
            "url":          f"https://reddit.com{post.permalink}",
            "flair":        post.link_flair_text,
        })

    return json.dumps({
        "query":      query,
        "subreddits": scoped or ["all"],
        "sort":       sort,
        "total":      len(posts),
        "posts":      posts,
    }, ensure_ascii=False, indent=2)


# ── YouTube ───────────────────────────────────────────────────────────────────

@mcp.tool()
def youtube_search(
    query: str,
    max_results: int = 15,
    order: str = "viewCount",
) -> str:
    """
    Search YouTube videos by keyword.

    Args:
        query: Search query (e.g. "Zepto vs Blinkit review")
        max_results: Max videos to return (default 15, max 50)
        order: Sort order — viewCount, relevance, date (default: viewCount)
    """
    import requests

    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        return json.dumps({"error": "YOUTUBE_API_KEY not configured on server"})

    max_results = min(max_results, 50)
    BASE = "https://www.googleapis.com/youtube/v3"

    def api(endpoint, params):
        params["key"] = api_key
        r = requests.get(f"{BASE}/{endpoint}", params=params, timeout=15)
        r.raise_for_status()
        return r.json()

    search_data = api("search", {
        "part": "snippet", "q": query, "type": "video",
        "maxResults": max_results, "order": order,
    })
    items = search_data.get("items", [])
    if not items:
        return json.dumps({"query": query, "results": []})

    video_ids = [i["id"]["videoId"] for i in items]
    stats_data = api("videos", {"part": "statistics,contentDetails", "id": ",".join(video_ids)})
    stats_map = {v["id"]: v for v in stats_data.get("items", [])}

    results = []
    for item in items:
        vid_id = item["id"]["videoId"]
        snip   = item["snippet"]
        stats  = stats_map.get(vid_id, {}).get("statistics", {})
        results.append({
            "video_id":     vid_id,
            "title":        snip.get("title"),
            "channel":      snip.get("channelTitle"),
            "published_at": snip.get("publishedAt"),
            "description":  (snip.get("description") or "")[:200],
            "views":        int(stats.get("viewCount", 0)),
            "likes":        int(stats.get("likeCount", 0)),
            "comments":     int(stats.get("commentCount", 0)),
            "url":          f"https://youtube.com/watch?v={vid_id}",
        })

    return json.dumps({
        "query":   query,
        "order":   order,
        "total":   len(results),
        "results": results,
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def youtube_channel(
    handle: str,
    max_videos: int = 20,
) -> str:
    """
    Get stats and top videos for a YouTube channel.

    Args:
        handle: Channel handle or ID (e.g. "@Zepto" or "UCxxxxxxxx")
        max_videos: Max videos to return (default 20, max 50)
    """
    import requests

    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        return json.dumps({"error": "YOUTUBE_API_KEY not configured on server"})

    max_videos = min(max_videos, 50)
    BASE = "https://www.googleapis.com/youtube/v3"

    def api(endpoint, params):
        params["key"] = api_key
        r = requests.get(f"{BASE}/{endpoint}", params=params, timeout=15)
        r.raise_for_status()
        return r.json()

    # Resolve channel
    if handle.startswith("UC"):
        data = api("channels", {"part": "snippet,statistics,contentDetails", "id": handle})
    else:
        data = api("channels", {"part": "snippet,statistics,contentDetails", "forHandle": handle.lstrip("@")})

    items = data.get("items", [])
    if not items:
        return json.dumps({"error": f"Channel not found: {handle}"})

    ch    = items[0]
    stats = ch.get("statistics", {})
    channel_info = {
        "channel_id":  ch["id"],
        "title":       ch["snippet"]["title"],
        "description": ch["snippet"].get("description", "")[:300],
        "country":     ch["snippet"].get("country"),
        "subscribers": stats.get("subscriberCount"),
        "total_views": stats.get("viewCount"),
        "video_count": stats.get("videoCount"),
        "url":         f"https://youtube.com/channel/{ch['id']}",
    }

    uploads = ch.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
    videos = []
    if uploads:
        next_token = None
        while len(videos) < max_videos:
            params = {
                "part": "snippet,contentDetails",
                "playlistId": uploads,
                "maxResults": min(50, max_videos - len(videos)),
            }
            if next_token:
                params["pageToken"] = next_token
            pl_data = api("playlistItems", params)
            pl_items = pl_data.get("items", [])
            if not pl_items:
                break
            vid_ids   = [i["contentDetails"]["videoId"] for i in pl_items]
            st_data   = api("videos", {"part": "statistics", "id": ",".join(vid_ids)})
            st_map    = {v["id"]: v for v in st_data.get("items", [])}
            for item in pl_items:
                vid_id = item["contentDetails"]["videoId"]
                snip   = item["snippet"]
                st     = st_map.get(vid_id, {}).get("statistics", {})
                videos.append({
                    "video_id":     vid_id,
                    "title":        snip.get("title"),
                    "published_at": snip.get("publishedAt"),
                    "views":        int(st.get("viewCount", 0)),
                    "likes":        int(st.get("likeCount", 0)),
                    "comments":     int(st.get("commentCount", 0)),
                    "url":          f"https://youtube.com/watch?v={vid_id}",
                })
            next_token = pl_data.get("nextPageToken")
            if not next_token:
                break
        videos.sort(key=lambda v: v["views"], reverse=True)

    return json.dumps({
        "channel":    channel_info,
        "top_videos": videos,
    }, ensure_ascii=False, indent=2)


# ── Play Store ────────────────────────────────────────────────────────────────

@mcp.tool()
def play_store_reviews(
    package_id: str,
    max_reviews: int = 100,
    country: str = "in",
) -> str:
    """
    Fetch Google Play Store reviews for an app.

    Args:
        package_id: App package ID (e.g. "com.zepto.app") or full Play Store URL
        max_reviews: Max reviews to fetch (default 100, max 200)
        country: Two-letter country code (default: in for India)
    """
    from urllib.parse import parse_qs, urlparse
    from google_play_scraper import Sort, reviews as gps_reviews

    max_reviews = min(max_reviews, 200)

    # Accept full URL or bare package ID
    if package_id.startswith("http"):
        qs = parse_qs(urlparse(package_id).query)
        if "id" not in qs:
            return json.dumps({"error": "Could not find ?id= in URL"})
        package_id = qs["id"][0]

    all_reviews = []
    token = None

    while len(all_reviews) < max_reviews:
        remaining = max_reviews - len(all_reviews)
        try:
            batch, token = gps_reviews(
                package_id,
                lang="en",
                country=country,
                sort=Sort.NEWEST,
                count=min(200, remaining),
                continuation_token=token,
            )
        except Exception as e:
            return json.dumps({"error": str(e), "package_id": package_id})

        if not batch:
            break
        all_reviews.extend(batch)
        if token is None:
            break
        time.sleep(0.5)

    clean = []
    for r in all_reviews[:max_reviews]:
        clean.append({
            "rating":      r.get("score"),
            "date":        r.get("at").isoformat() if r.get("at") else None,
            "review_text": r.get("content"),
            "thumbs_up":   r.get("thumbsUpCount", 0),
            "app_version": r.get("appVersion"),
        })

    ratings = [r["rating"] for r in clean if r["rating"]]
    avg = round(sum(ratings) / len(ratings), 2) if ratings else None

    return json.dumps({
        "package_id":    package_id,
        "country":       country,
        "total_reviews": len(clean),
        "avg_rating":    avg,
        "reviews":       clean,
    }, ensure_ascii=False, indent=2)


# ── App Store ─────────────────────────────────────────────────────────────────

@mcp.tool()
def app_store_reviews(
    app_id: str,
    max_reviews: int = 100,
    country: str = "in",
) -> str:
    """
    Fetch iOS App Store reviews for an app.

    Args:
        app_id: iTunes numeric app ID (e.g. "123456789")
        max_reviews: Max reviews to fetch (default 100, max 500)
        country: Two-letter country code (default: in for India)
    """
    import requests

    max_reviews = min(max_reviews, 500)
    RSS_URL = "https://itunes.apple.com/{country}/rss/customerreviews/page={page}/id={app_id}/sortby=mostrecent/json"

    all_reviews = []
    for page in range(1, 11):
        if len(all_reviews) >= max_reviews:
            break
        url = RSS_URL.format(country=country, page=page, app_id=app_id)
        try:
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            entries = r.json().get("feed", {}).get("entry", [])
            if not entries or isinstance(entries, dict):
                break
            for entry in entries:
                if isinstance(entry, dict) and "im:rating" in entry:
                    all_reviews.append({
                        "rating":      int(entry.get("im:rating", {}).get("label", 0)),
                        "title":       entry.get("title", {}).get("label"),
                        "review_text": entry.get("content", {}).get("label"),
                        "version":     entry.get("im:version", {}).get("label"),
                        "date":        entry.get("updated", {}).get("label"),
                    })
            time.sleep(0.3)
        except Exception as e:
            break

    all_reviews = all_reviews[:max_reviews]
    ratings = [r["rating"] for r in all_reviews if r.get("rating")]
    avg = round(sum(ratings) / len(ratings), 2) if ratings else None

    return json.dumps({
        "app_id":        app_id,
        "country":       country,
        "total_reviews": len(all_reviews),
        "avg_rating":    avg,
        "reviews":       all_reviews,
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def app_store_search(
    query: str,
    country: str = "in",
    limit: int = 10,
) -> str:
    """
    Search the iOS App Store by keyword — returns app IDs and metadata.

    Args:
        query: Search keyword (e.g. "grocery delivery india")
        country: Two-letter country code (default: in)
        limit: Max results (default 10)
    """
    import requests

    params = {"term": query, "country": country, "media": "software", "limit": limit}
    r = requests.get("https://itunes.apple.com/search", params=params, timeout=15)
    r.raise_for_status()
    results = r.json().get("results", [])

    apps = [{
        "app_id":       a.get("trackId"),
        "name":         a.get("trackName"),
        "developer":    a.get("artistName"),
        "price":        a.get("price"),
        "rating":       a.get("averageUserRating"),
        "rating_count": a.get("userRatingCount"),
        "category":     a.get("primaryGenreName"),
        "url":          a.get("trackViewUrl"),
        "description":  (a.get("description") or "")[:300],
    } for a in results]

    return json.dumps({"query": query, "country": country, "total": len(apps), "apps": apps},
                      ensure_ascii=False, indent=2)


# ── Google Trends ─────────────────────────────────────────────────────────────

@mcp.tool()
def google_trends(
    keywords: str,
    geo: str = "IN",
    timeframe: str = "today 12-m",
) -> str:
    """
    Get Google Trends data — interest over time, regional breakdown, related queries.

    Args:
        keywords: Comma-separated keywords to compare, max 5 (e.g. "Zepto,Blinkit,Swiggy Instamart")
        geo: Country/region code (default: IN for India). Use "" for worldwide.
        timeframe: Time range — "today 1-m", "today 3-m", "today 12-m", "today 5-y", "all" (default: today 12-m)
    """
    from pytrends.request import TrendReq

    kws = [k.strip() for k in keywords.split(",")][:5]

    pt = TrendReq(hl="en-US", tz=330)
    pt.build_payload(kws, cat=0, timeframe=timeframe, geo=geo, gprop="")

    result = {
        "keywords":  kws,
        "geo":       geo,
        "timeframe": timeframe,
        "fetched_at": datetime.now().isoformat(),
    }

    # Interest over time
    try:
        df = pt.interest_over_time()
        if not df.empty:
            iot = {}
            for kw in kws:
                if kw in df.columns:
                    s = df[kw]
                    iot[kw] = {
                        "avg":        round(float(s.mean()), 1),
                        "max":        int(s.max()),
                        "trend":      "rising" if s.iloc[-1] > s.iloc[0] else "falling",
                        "last_value": int(s.iloc[-1]),
                        "time_series": {str(k): int(v) for k, v in s.items()},
                    }
            result["interest_over_time"] = iot
    except Exception as e:
        result["interest_over_time"] = {"error": str(e)}

    time.sleep(1)

    # Regional breakdown
    try:
        pt.build_payload(kws, cat=0, timeframe=timeframe, geo=geo, gprop="")
        df = pt.interest_by_region(resolution="REGION", inc_low_vol=True, inc_geo_code=True)
        if not df.empty:
            ibr = {}
            for kw in kws:
                if kw in df.columns:
                    top = df[kw].sort_values(ascending=False).head(10)
                    ibr[kw] = {str(idx): int(val) for idx, val in top.items()}
            result["interest_by_region"] = ibr
    except Exception as e:
        result["interest_by_region"] = {"error": str(e)}

    time.sleep(1)

    # Related queries
    try:
        pt.build_payload(kws, cat=0, timeframe=timeframe, geo=geo, gprop="")
        rq_data = pt.related_queries()
        rq = {}
        for kw in kws:
            kw_data = rq_data.get(kw, {})
            top_df    = kw_data.get("top")
            rising_df = kw_data.get("rising")
            rq[kw] = {
                "top":    top_df.to_dict("records") if top_df is not None and not top_df.empty else [],
                "rising": rising_df.to_dict("records") if rising_df is not None and not rising_df.empty else [],
            }
        result["related_queries"] = rq
    except Exception as e:
        result["related_queries"] = {"error": str(e)}

    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
