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

    return tasks


def phase2(config_path: str):
    config_file = Path(config_path)
    if not config_file.exists():
        print(f"Config not found: {config_path}")
        sys.exit(1)

    config   = json.loads(config_file.read_text())
    data_dir = config_file.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # Meta Ads: write a runner config, executed separately after parallel tasks
    meta_ads = config.get("meta_ads", [])
    meta_config_path = None
    if meta_ads:
        meta_cfg = {
            "config": {
                "default_max_ads_per_competitor": 15,
                "output_directory": str(data_dir / "meta_ads"),
            },
            "competitors": [
                {"name": a["name"], "page_id": a["page_id"], "url": a.get("url", "")}
                for a in meta_ads if a.get("page_id")
            ],
        }
        meta_config_path = data_dir / "meta_ads_config.json"
        meta_config_path.write_text(json.dumps(meta_cfg, indent=2))

    tasks = build_tasks(config, data_dir)
    total = len(tasks) + (1 if meta_config_path else 0)

    print(f"\n{'='*60}")
    print(f"  Phase 2 — Data Extraction")
    print(f"  Topic:  {config['topic']}")
    print(f"  Tasks:  {len(tasks)} parallel + {'meta ads (sequential)' if meta_config_path else 'no meta ads'}")
    print(f"{'='*60}\n")

    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(run, label, cmd): label for label, cmd in tasks}
        done = 0
        for future in as_completed(futures):
            done += 1
            label, success, out = future.result()
            icon = "✅" if success else "❌"
            print(f"  [{done:>2}/{len(tasks)}] {icon} {label}")
            if not success:
                for line in out.splitlines()[-3:]:
                    print(f"           {line}")
            results.append((label, success))

    # Meta Ads — sequential (Playwright + Gemini, slow)
    if meta_config_path:
        print(f"\n  Running Meta Ads (Playwright + Gemini, sequential)...")
        label, success, out = run(
            f"meta_ads ({len(meta_ads)} brands)",
            ["uv", "run", "python", "tools/meta_ads_runner.py", str(meta_config_path)],
        )
        icon = "✅" if success else "❌"
        print(f"  {icon} {label}")
        if not success:
            for line in out.splitlines()[-5:]:
                print(f"       {line}")
        results.append((label, success))

    passed = sum(1 for _, s in results if s)
    failed = [l for l, s in results if not s]

    print(f"\n{'='*60}")
    print(f"  Done: {passed}/{total} succeeded")
    if failed:
        print(f"  Failed: {', '.join(f[:40] for f in failed)}")
    print(f"\n  Data → {data_dir}/")
    print(f"  Next:   uv run python phase3.py {config_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: uv run python phase2.py research/<slug>/config.json")
        sys.exit(1)
    phase2(sys.argv[1])
