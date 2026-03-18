"""
Reddit Research Tool
Search subreddits for pain points, user sentiment, and market signals.

Usage:
    uv run python tools/reddit.py --search "astrology app india" --subreddits india,personalfinanceindia --max 100
    uv run python tools/reddit.py --search "kids homework help" --max 50
    uv run python tools/reddit.py --subreddit india --search "astrology" --sort top --max 100

Requires in .env:
    REDDIT_CLIENT_ID=...
    REDDIT_CLIENT_SECRET=...
    REDDIT_USER_AGENT=ResearchBot/1.0
"""
import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import praw
from dotenv import load_dotenv

load_dotenv()


def _get_reddit() -> praw.Reddit:
    client_id     = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    user_agent    = os.environ.get("REDDIT_USER_AGENT", "ResearchBot/1.0")

    if not client_id or client_id == "your_reddit_client_id_here":
        print("❌ REDDIT_CLIENT_ID not set in .env", file=sys.stderr)
        sys.exit(1)

    return praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent,
    )


# ── Search ────────────────────────────────────────────────────────────────────

def search_posts(query: str, subreddits: list[str] | None = None,
                 max_posts: int = 100, sort: str = "relevance",
                 time_filter: str = "all") -> list:
    reddit = _get_reddit()
    target = "+".join(subreddits) if subreddits else "all"
    print(f"\n🔍 Reddit search: '{query}' in r/{target} (sort={sort}, time={time_filter})")

    posts = []
    try:
        sub = reddit.subreddit(target)
        for post in sub.search(query, sort=sort, time_filter=time_filter, limit=max_posts):
            posts.append({
                "post_id":     post.id,
                "title":       post.title,
                "selftext":    (post.selftext or "")[:2000],
                "score":       post.score,
                "upvote_ratio": post.upvote_ratio,
                "num_comments": post.num_comments,
                "subreddit":   str(post.subreddit),
                "author":      str(post.author) if post.author else "[deleted]",
                "created_utc": datetime.fromtimestamp(post.created_utc).isoformat(),
                "url":         f"https://reddit.com{post.permalink}",
                "flair":       post.link_flair_text,
                "is_self":     post.is_self,
                "top_comments": _get_top_comments(post, 5),
            })
            print(f"  {post.score:>6} pts | r/{post.subreddit:<20} | {post.title[:70]}")
    except Exception as e:
        print(f"  ⚠️  Error: {e}")

    print(f"\n  ✅ {len(posts)} posts fetched")
    return posts


def _get_top_comments(post, n: int = 5) -> list:
    try:
        post.comments.replace_more(limit=0)
        comments = sorted(post.comments.list()[:20], key=lambda c: getattr(c, "score", 0), reverse=True)
        return [
            {
                "body":   (c.body or "")[:500],
                "score":  getattr(c, "score", 0),
                "author": str(getattr(c, "author", "[deleted]")),
            }
            for c in comments[:n]
            if hasattr(c, "body") and c.body not in ("[deleted]", "[removed]")
        ]
    except Exception:
        return []


# ── Subreddit top posts ───────────────────────────────────────────────────────

def fetch_subreddit_top(subreddit: str, sort: str = "top",
                        time_filter: str = "year", max_posts: int = 50) -> list:
    reddit = _get_reddit()
    print(f"\n📋 r/{subreddit} — {sort} posts ({time_filter})")
    posts = []
    try:
        sub = getattr(reddit.subreddit(subreddit), sort)
        for post in sub(time_filter=time_filter, limit=max_posts):
            posts.append({
                "post_id":      post.id,
                "title":        post.title,
                "selftext":     (post.selftext or "")[:1000],
                "score":        post.score,
                "num_comments": post.num_comments,
                "created_utc":  datetime.fromtimestamp(post.created_utc).isoformat(),
                "url":          f"https://reddit.com{post.permalink}",
                "flair":        post.link_flair_text,
            })
            print(f"  {post.score:>6} pts | {post.num_comments:>4} comments | {post.title[:80]}")
    except Exception as e:
        print(f"  ⚠️  Error: {e}")

    print(f"\n  ✅ {len(posts)} posts")
    return posts


# ── Save ──────────────────────────────────────────────────────────────────────

def save(name: str, posts: list, query: str, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "query":      query,
        "scraped_at": datetime.now().isoformat(),
        "total_posts": len(posts),
        "posts":      posts,
    }
    json_path = output_dir / "posts.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"  JSON → {json_path}")

    if posts:
        flat = [{k: v for k, v in p.items() if k != "top_comments"} for p in posts]
        csv_path = output_dir / "posts.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(flat[0].keys()))
            writer.writeheader()
            writer.writerows(flat)
        print(f"  CSV  → {csv_path}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Reddit research scraper")
    parser.add_argument("--search",     required=True, help="Search query")
    parser.add_argument("--subreddits", default=None,  help="Comma-separated subreddits (default: all)")
    parser.add_argument("--subreddit",  default=None,  help="Single subreddit for top posts")
    parser.add_argument("--sort",       default="relevance",
                        choices=["relevance", "hot", "top", "new", "comments"])
    parser.add_argument("--time",       default="all",
                        choices=["all", "year", "month", "week", "day"])
    parser.add_argument("--max",        type=int, default=100)
    parser.add_argument("--out",        default="data/reddit")
    args = parser.parse_args()

    subs = [s.strip() for s in args.subreddits.split(",")] if args.subreddits else None
    posts = search_posts(args.search, subs, args.max, args.sort, args.time)

    safe = args.search.replace(" ", "_")[:40]
    out  = Path(args.out) / safe
    save(safe, posts, args.search, out)
    print(f"\n✅ Done → {out}/")


if __name__ == "__main__":
    main()
