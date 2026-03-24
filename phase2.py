"""
Phase 2 — Data Extraction
Reads config.json and runs all research tools in parallel.
All output goes to research/<slug>/data/<tool>/

Usage:
    uv run python phase2.py research/companion-apps/config.json
"""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def run(label: str, cmd: list[str]) -> tuple[str, bool, str]:
    """Run a tool as a subprocess. Returns (label, success, output)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent,
        )
        success = result.returncode == 0
        out = result.stdout + (f"\n[stderr] {result.stderr}" if result.stderr.strip() else "")
        return label, success, out.strip()
    except Exception as e:
        return label, False, str(e)


def build_tasks(config: dict, data_dir: Path) -> list[tuple[str, list[str]]]:
    """Build the full list of (label, command) tasks from config."""
    tasks = []
    slug = config["slug"]

    # Web search
    for q in config.get("web_search", {}).get("queries", []):
        safe = q[:40].replace(" ", "_").replace("/", "-")
        out  = str(data_dir / "web_search" / safe)
        tasks.append((f"web: {q[:50]}", [
            "uv", "run", "python", "tools/web_search.py",
            "--query", q, "--out", out,
        ]))

    # China search
    for q in config.get("china_search", {}).get("queries", []):
        safe = q[:40].replace(" ", "_").replace("/", "-")
        out  = str(data_dir / "china_search" / safe)
        tasks.append((f"china: {q[:50]}", [
            "uv", "run", "python", "tools/china_search.py",
            "--query", q, "--out", out,
        ]))

    # Play Store reviews
    for pkg in config.get("play_store", []):
        out = str(data_dir / "play_store" / pkg)
        tasks.append((f"play_store: {pkg}", [
            "uv", "run", "python", "tools/play_store.py",
            pkg, "--max", "500", "--out", out,
        ]))

    # App Store reviews
    for app_id in config.get("app_store", []):
        out = str(data_dir / "app_store" / app_id)
        tasks.append((f"app_store: {app_id}", [
            "uv", "run", "python", "tools/app_store.py",
            "--app-id", app_id, "--max", "200", "--out", out,
        ]))

    # Reddit — queries
    for q in config.get("reddit", {}).get("queries", []):
        subs = ",".join(config.get("reddit", {}).get("subreddits", []))
        safe = q[:40].replace(" ", "_").replace("/", "-")
        out  = str(data_dir / "reddit" / safe)
        cmd = ["uv", "run", "python", "tools/reddit.py",
               "--search", q, "--max", "50", "--comments", "--out", out]
        if subs:
            cmd += ["--subreddits", subs]
        tasks.append((f"reddit: {q[:50]}", cmd))

    # Reddit — subreddits (top posts)
    for sub in config.get("reddit", {}).get("subreddits", []):
        out = str(data_dir / "reddit" / f"r_{sub}")
        tasks.append((f"reddit r/{sub}", [
            "uv", "run", "python", "tools/reddit.py",
            "--subreddit", sub, "--sort", "top", "--max", "50", "--comments", "--out", out,
        ]))

    # YouTube — channel stats
    for handle in config.get("youtube", {}).get("channels", []):
        safe = handle.lstrip("@")
        out  = str(data_dir / "youtube" / safe)
        tasks.append((f"youtube channel: {handle}", [
            "uv", "run", "python", "tools/youtube.py",
            "--channel", handle, "--max-videos", "50", "--out", out,
        ]))

    # YouTube — search queries
    for q in config.get("youtube", {}).get("search_queries", []):
        safe = q[:40].replace(" ", "_").replace("/", "-")
        out  = str(data_dir / "youtube" / f"search_{safe}")
        tasks.append((f"youtube search: {q[:50]}", [
            "uv", "run", "python", "tools/youtube.py",
            "--search", q, "--max", "10", "--out", out,
        ]))

    # Google Trends
    trends = config.get("google_trends", {})
    if trends.get("keywords"):
        out = str(data_dir / "google_trends")
        tasks.append(("google_trends", [
            "uv", "run", "python", "tools/google_trends.py",
            "--keywords", trends["keywords"],
            "--geo", trends.get("geo", "IN"),
            "--out", out,
        ]))

    # Trustpilot
    for slug_tp in config.get("trustpilot", []):
        out = str(data_dir / "trustpilot" / slug_tp)
        tasks.append((f"trustpilot: {slug_tp}", [
            "uv", "run", "python", "tools/trustpilot.py",
            "--company", slug_tp, "--max", "200", "--out", out,
        ]))

    # Meta Ads
    for entry in config.get("meta_ads", []):
        if not entry.get("page_id"):
            continue
        name = entry["name"].replace(" ", "_")
        out  = str(data_dir / "meta_ads" / name)
        cmd  = ["uv", "run", "python", "tools/meta_ads_runner.py",
                "--page-id", entry["page_id"], "--name", entry["name"],
                "--out", out]
        if entry.get("url"):
            cmd += ["--url", entry["url"]]
        tasks.append((f"meta_ads: {entry['name']}", cmd))

    return tasks


def phase2(config_path: str):
    config_file = Path(config_path)
    if not config_file.exists():
        print(f"Config not found: {config_path}")
        sys.exit(1)

    config   = json.loads(config_file.read_text())
    slug     = config["slug"]
    data_dir = config_file.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  Phase 2 — Data Extraction")
    print(f"  Topic: {config['topic']}")
    print(f"{'='*60}\n")

    tasks = build_tasks(config, data_dir)
    print(f"  {len(tasks)} tasks to run in parallel...\n")

    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(run, label, cmd): label for label, cmd in tasks}
        done = 0
        for future in as_completed(futures):
            done += 1
            label, success, out = future.result()
            status = "OK" if success else "FAIL"
            print(f"  [{done:>2}/{len(tasks)}] [{status}] {label}")
            if not success:
                print(f"         {out[:200]}")
            results.append((label, success))

    ok    = sum(1 for _, s in results if s)
    fails = [(l, ) for l, s in results if not s]

    print(f"\n{'='*60}")
    print(f"  Done: {ok}/{len(tasks)} succeeded")
    if fails:
        print(f"  Failed:")
        for (l,) in fails:
            print(f"    - {l}")
    print(f"\n  Data → {data_dir}/")
    print(f"  Run Phase 3:  uv run python phase3.py {config_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: uv run python phase2.py research/<slug>/config.json")
        sys.exit(1)
    phase2(sys.argv[1])
