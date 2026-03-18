"""
Reddit Research Tool
Search posts across Reddit or browse a specific subreddit.

Usage:
    uv run python tools/reddit.py --search "kids homework app india" --max 50
    uv run python tools/reddit.py --search "homework help" --subreddits india,indianparents --max 100
    uv run python tools/reddit.py --subreddit IndiaInvestments --sort hot --max 50
    uv run python tools/reddit.py --search "query" --comments --max 25

Flags:
    --search       Search query across all of Reddit (or scoped to --subreddits)
    --subreddit    Browse a single subreddit directly
    --subreddits   Comma-separated subreddits to scope a --search query
    --sort         Sort order: relevance, hot, top, new, comments (default: relevance)
    --max          Max posts to fetch (default: 50)
    --comments     Also fetch top comments for each post
    --out          Output directory (default: data/reddit)

Requires:
    REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET in .env
    Get them at: reddit.com/prefs/apps → create script app
"""
import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import praw
from dotenv import load_dotenv

load_dotenv()

IMAGE_RE = re.compile(r"https?://\S+\.(?:png|jpg|jpeg|gif|bmp|svg|webp)", re.IGNORECASE)


# ── Auth ──────────────────────────────────────────────────────────────────────

def _build_reddit() -> praw.Reddit:
    client_id     = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("❌ REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET not set in .env", file=sys.stderr)
        print("   Get them at: reddit.com/prefs/apps → create script app", file=sys.stderr)
        sys.exit(1)
    return praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent="research-tool/2.0",
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    """Strip image URLs and collapse whitespace."""
    if not text:
        return ""
    text = IMAGE_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def _ts(utc_float) -> str:
    return datetime.fromtimestamp(utc_float, tz=timezone.utc).isoformat()


def _serialise_post(post, fetch_comments: bool = False) -> dict:
    top_comments = []
    if fetch_comments:
        try:
            post.comments.replace_more(limit=0)
            for c in sorted(post.comments.list(), key=lambda x: x.score, reverse=True)[:10]:
                body = _clean(getattr(c, "body", ""))
                if body:
                    top_comments.append({
                        "author": str(c.author) if c.author else "[deleted]",
                        "score":  c.score,
                        "text":   body,
                        "date":   _ts(c.created_utc),
                    })
        except Exception:
            pass

    return {
        "post_id":    post.id,
        "title":      _clean(post.title),
        "text":       _clean(post.selftext),
        "url":        post.url,
        "permalink":  f"https://reddit.com{post.permalink}",
        "subreddit":  str(post.subreddit),
        "author":     str(post.author) if post.author else "[deleted]",
        "score":      post.score,
        "upvote_ratio": post.upvote_ratio,
        "num_comments": post.num_comments,
        "date":       _ts(post.created_utc),
        "flair":      post.link_flair_text,
        "top_comments": top_comments,
    }


# ── Fetch ─────────────────────────────────────────────────────────────────────

def search_posts(reddit: praw.Reddit, query: str, subreddits: list[str],
                 sort: str, max_posts: int, fetch_comments: bool) -> list[dict]:
    scope = "+".join(subreddits) if subreddits else "all"
    print(f"\n🔍 Searching r/{scope}: '{query}' (sort={sort}, max={max_posts})")

    sub = reddit.subreddit(scope)
    results = []
    for post in sub.search(query, sort=sort, limit=max_posts):
        results.append(_serialise_post(post, fetch_comments))
        print(f"  {post.score:>6} pts | r/{str(post.subreddit):<20} | {post.title[:60]}")

    print(f"\n  ✅ {len(results)} posts fetched")
    return results


def browse_subreddit(reddit: praw.Reddit, subreddit: str, sort: str,
                     max_posts: int, fetch_comments: bool) -> list[dict]:
    print(f"\n📋 Browsing r/{subreddit} (sort={sort}, max={max_posts})")
    sub = reddit.subreddit(subreddit)

    sort_fn = {
        "hot":  sub.hot,
        "new":  sub.new,
        "top":  sub.top,
        "rising": sub.rising,
    }.get(sort, sub.hot)

    results = []
    for post in sort_fn(limit=max_posts):
        results.append(_serialise_post(post, fetch_comments))
        print(f"  {post.score:>6} pts | {post.title[:70]}")

    print(f"\n  ✅ {len(results)} posts fetched")
    return results


# ── Save ──────────────────────────────────────────────────────────────────────

def save(name: str, posts: list[dict], meta: dict, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = {**meta, "total": len(posts), "posts": posts}
    json_path = output_dir / "posts.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"  JSON → {json_path}")

    if posts:
        csv_path = output_dir / "posts.csv"
        flat_keys = [k for k in posts[0].keys() if k != "top_comments"]
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=flat_keys, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(posts)
        print(f"  CSV  → {csv_path}")

    # Stats
    scores = [p["score"] for p in posts]
    if scores:
        print(f"\n  ── Stats ──────────────────────────────")
        print(f"  Posts:        {len(posts)}")
        print(f"  Avg score:    {sum(scores) / len(scores):.0f}")
        print(f"  Top score:    {max(scores)}")
        subreddits = {}
        for p in posts:
            subreddits[p["subreddit"]] = subreddits.get(p["subreddit"], 0) + 1
        top_subs = sorted(subreddits.items(), key=lambda x: x[1], reverse=True)[:5]
        print(f"  Top subreddits: {', '.join(f'r/{s}({n})' for s, n in top_subs)}")
        print(f"  ───────────────────────────────────────")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Reddit research tool")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--search",    help="Search query")
    group.add_argument("--subreddit", help="Browse a specific subreddit")
    parser.add_argument("--subreddits", help="Comma-separated subreddits to scope search (e.g. india,indianparents)")
    parser.add_argument("--sort",     default="relevance",
                        choices=["relevance", "hot", "top", "new", "comments"])
    parser.add_argument("--max",      type=int, default=50)
    parser.add_argument("--comments", action="store_true", help="Fetch top comments per post")
    parser.add_argument("--out",      default="data/reddit")
    args = parser.parse_args()

    reddit = _build_reddit()

    if args.search:
        scoped = [s.strip() for s in args.subreddits.split(",")] if args.subreddits else []
        posts = search_posts(reddit, args.search, scoped, args.sort, args.max, args.comments)
        safe  = args.search.replace(" ", "_")[:40]
        name  = safe
        meta  = {
            "query": args.search,
            "subreddits": scoped or ["all"],
            "sort": args.sort,
            "fetched_at": datetime.now().isoformat(),
        }
        out = Path(args.out) / safe
    else:
        posts = browse_subreddit(reddit, args.subreddit, args.sort, args.max, args.comments)
        name  = args.subreddit
        meta  = {
            "subreddit": args.subreddit,
            "sort": args.sort,
            "fetched_at": datetime.now().isoformat(),
        }
        out = Path(args.out) / args.subreddit

    save(name, posts, meta, out)
    print(f"\n✅ Done → {out}/")


if __name__ == "__main__":
    main()
