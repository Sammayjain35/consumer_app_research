"""
compile_rich.py — Rich HTML Report Compiler
Assembles sectional markdown files into a polished, chart-rich HTML report.
Reusable across any research topic.

Usage:
    uv run python compile_rich.py research/companion-apps/config.json

Output:
    research/<slug>/report.html   ← rich HTML with charts, stat boxes, pull quotes
    research/<slug>/report.md     ← plain markdown (for reference)
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime


SECTIONS = {
    1: "Executive Summary",
    2: "Market Overview",
    3: "Competitor Landscape",
    4: "Consumer Voice",
    5: "Content & Ads Intelligence",
    6: "Trends & Momentum",
    7: "Opportunities & Gaps",
    8: "Sources & Data",
}


# ── Data extractors ────────────────────────────────────────────────────────────

def extract_stats(text: str) -> list[dict]:
    """Pull bold numbers/facts for stat callout boxes."""
    stats = []
    # Match **$X billion**, **X%**, **X million**, **₹X**, etc.
    pattern = r'\*\*([^*]{3,60}(?:\$[\d,.]+\s*(?:billion|million|B|M|K|Cr)|[\d,.]+%|[\d,.]+\s*(?:billion|million|Cr)|₹[\d,.]+\s*(?:Cr|K|M)?)[^*]{0,40})\*\*'
    for m in re.finditer(pattern, text):
        val = m.group(1).strip()
        if len(val) < 80:
            stats.append(val)
    return list(dict.fromkeys(stats))[:12]  # dedupe, max 12


def extract_pull_quotes(text: str) -> list[str]:
    """Extract italicised user quotes (the *"..."* pattern)."""
    quotes = []
    for m in re.finditer(r'\*"([^"]{40,300})"\*', text):
        quotes.append(m.group(1).strip())
    return quotes[:8]


def load_play_store_ratings(data_dir: Path) -> dict:
    """Return {app_short_name: avg_rating} from play store data."""
    ratings = {}
    ps_dir = data_dir / "play_store"
    if not ps_dir.exists():
        return ratings
    for d in ps_dir.iterdir():
        f = d / "play_store_reviews.json"
        if not f.exists():
            continue
        try:
            raw = json.loads(f.read_text())
            reviews = raw.get("reviews", [])
            r_vals = [r["rating"] for r in reviews if r.get("rating")]
            if r_vals:
                name = d.name.split(".")[-1].replace("app", "").replace("twa", "").strip(".")
                name = name[:16].title() if name else d.name[:16]
                ratings[name] = round(sum(r_vals) / len(r_vals), 1)
        except Exception:
            pass
    return dict(sorted(ratings.items(), key=lambda x: x[1], reverse=True))


def load_trends_regions(data_dir: Path) -> dict:
    """Return {keyword: [(region, score)...]} top 5 regions."""
    trends_dir = data_dir / "google_trends"
    if not trends_dir.exists():
        return {}
    files = list(trends_dir.glob("*.json"))
    if not files:
        return {}
    try:
        d = json.loads(files[0].read_text())
        out = {}
        for kw, regions in (d.get("interest_by_region") or {}).items():
            if isinstance(regions, dict):
                top = sorted(regions.items(), key=lambda x: x[1], reverse=True)[:5]
                if top:
                    out[kw] = top
        return out
    except Exception:
        return {}


def parse_market_numbers(discovery: dict) -> list[dict]:
    """Extract market size numbers from discovery text for chart."""
    markets = []
    for geo, label in [("global", "Global"), ("india", "India"), ("china", "China")]:
        text = discovery.get(geo, "")
        # Look for $X billion or $X.X billion patterns
        m = re.search(r'\$\s*([\d.]+)\s*(billion|B)\b', text, re.I)
        if m:
            markets.append({"label": label, "value": float(m.group(1))})
    return markets


# ── Markdown → HTML ────────────────────────────────────────────────────────────

def md_to_html(text: str) -> str:
    """Minimal markdown to HTML — tables, bold, italic, headers, lists, blockquotes."""
    lines = text.split("\n")
    out = []
    in_table = False
    in_ul = False
    in_ol = False

    def close_lists():
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    def inline(s):
        # Bold
        s = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
        # Italic (but not bold)
        s = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<em>\1</em>', s)
        # Inline code
        s = re.sub(r'`(.+?)`', r'<code>\1</code>', s)
        # Links
        s = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', s)
        return s

    i = 0
    while i < len(lines):
        line = lines[i]

        # Table detection
        if "|" in line and i + 1 < len(lines) and re.match(r'[\|\s\-:]+$', lines[i + 1]):
            close_lists()
            if in_table:
                out.append("</tbody></table>")
            in_table = True
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            out.append('<div class="table-wrap"><table><thead><tr>')
            out.extend(f"<th>{inline(c)}</th>" for c in cells)
            out.append("</tr></thead><tbody>")
            i += 2  # skip separator
            continue

        if in_table and "|" in line:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            out.append("<tr>")
            out.extend(f"<td>{inline(c)}</td>" for c in cells)
            out.append("</tr>")
            i += 1
            continue
        elif in_table:
            out.append("</tbody></table></div>")
            in_table = False

        # Headers
        if line.startswith("#### "):
            close_lists()
            out.append(f"<h4>{inline(line[5:])}</h4>")
        elif line.startswith("### "):
            close_lists()
            out.append(f"<h3>{inline(line[4:])}</h3>")
        elif line.startswith("## "):
            close_lists()
            out.append(f"<h2>{inline(line[3:])}</h2>")
        elif line.startswith("# "):
            close_lists()
            out.append(f"<h1>{inline(line[2:])}</h1>")
        # Blockquote
        elif line.startswith("> "):
            close_lists()
            out.append(f"<blockquote>{inline(line[2:])}</blockquote>")
        # HR
        elif re.match(r'^---+$', line.strip()):
            close_lists()
            out.append("<hr>")
        # Unordered list
        elif re.match(r'^[-*] ', line):
            if not in_ul:
                close_lists()
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{inline(line[2:].strip())}</li>")
        # Ordered list
        elif re.match(r'^\d+\. ', line):
            if not in_ol:
                close_lists()
                out.append("<ol>")
                in_ol = True
            out.append(f"<li>{inline(re.sub(r'^\d+\. ', '', line))}</li>")
        # Empty line
        elif line.strip() == "":
            close_lists()
            out.append("")
        # Paragraph
        else:
            close_lists()
            if line.strip():
                out.append(f"<p>{inline(line)}</p>")

        i += 1

    close_lists()
    if in_table:
        out.append("</tbody></table></div>")

    return "\n".join(out)


# ── Chart builders (returns JS data objects) ──────────────────────────────────

def build_market_chart(markets: list[dict]) -> str:
    if not markets:
        return ""
    labels = json.dumps([m["label"] for m in markets])
    values = json.dumps([m["value"] for m in markets])
    colors = json.dumps(["#0055cc", "#00a878", "#f4a261"])
    return f"""
<div class="chart-card">
  <h4>Market Size Comparison ($ Billion, 2024–2025)</h4>
  <div class="chart-wrap"><canvas id="marketChart"></canvas></div>
</div>
<script>
new Chart(document.getElementById('marketChart'), {{
  type: 'bar',
  data: {{
    labels: {labels},
    datasets: [{{ label: 'Market Size ($B)', data: {values},
      backgroundColor: {colors}, borderRadius: 6 }}]
  }},
  options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }},
    scales: {{ y: {{ beginAtZero: true, ticks: {{ callback: v => '$' + v + 'B' }} }} }} }}
}});
</script>"""


def build_ratings_chart(ratings: dict) -> str:
    if not ratings:
        return ""
    labels = json.dumps(list(ratings.keys()))
    values = json.dumps(list(ratings.values()))
    colors = json.dumps([
        "#22c55e" if v >= 4.0 else "#f59e0b" if v >= 3.0 else "#ef4444"
        for v in ratings.values()
    ])
    return f"""
<div class="chart-card">
  <h4>Competitor App Ratings (Play Store avg)</h4>
  <div class="chart-wrap"><canvas id="ratingsChart"></canvas></div>
</div>
<script>
new Chart(document.getElementById('ratingsChart'), {{
  type: 'bar',
  data: {{
    labels: {labels},
    datasets: [{{ label: 'Avg Rating', data: {values},
      backgroundColor: {colors}, borderRadius: 6 }}]
  }},
  options: {{ indexAxis: 'y', responsive: true,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{ x: {{ min: 1, max: 5, ticks: {{ callback: v => v + '★' }} }} }} }}
}});
</script>"""


def build_trends_chart(trends: dict) -> str:
    # Pick the keyword with the most variance (most interesting)
    if not trends:
        return ""
    kw, top_regions = next(iter(trends.items()))
    if not top_regions:
        return ""
    labels = json.dumps([r[0] for r in top_regions])
    values = json.dumps([r[1] for r in top_regions])
    return f"""
<div class="chart-card">
  <h4>Search Interest by Region — "{kw}" (India)</h4>
  <div class="chart-wrap"><canvas id="trendsChart"></canvas></div>
</div>
<script>
new Chart(document.getElementById('trendsChart'), {{
  type: 'bar',
  data: {{
    labels: {labels},
    datasets: [{{ label: 'Interest', data: {values},
      backgroundColor: '#0055cc', borderRadius: 6 }}]
  }},
  options: {{ indexAxis: 'y', responsive: true,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{ x: {{ beginAtZero: true }} }} }}
}});
</script>"""


# ── Stat boxes ────────────────────────────────────────────────────────────────

def build_stat_boxes(stats: list[str]) -> str:
    if not stats:
        return ""
    boxes = "".join(f'<div class="stat-box">{s}</div>' for s in stats[:8])
    return f'<div class="stat-grid">{boxes}</div>'


# ── Pull quotes ───────────────────────────────────────────────────────────────

def build_pull_quote(quote: str) -> str:
    return f'<div class="pull-quote">"{quote}"</div>'


# ── Main compiler ──────────────────────────────────────────────────────────────

def compile_report(config_path: str):
    config_file = Path(config_path)
    config = json.loads(config_file.read_text())
    data_dir = config_file.parent / "data"
    sections_dir = config_file.parent / "sections"
    topic = config["topic"].title()
    slug = config["slug"]
    discovery = config.get("discovery", {})

    print(f"\n{'='*60}")
    print(f"  Compiling: {topic}")
    print(f"{'='*60}\n")

    # Load section files
    section_contents = {}
    for n, title in SECTIONS.items():
        path = sections_dir / f"section_{n:02d}.md"
        if path.exists():
            section_contents[n] = (title, path.read_text(encoding="utf-8"))
            print(f"  ✓ Section {n}: {title}")
        else:
            print(f"  ✗ Section {n}: {title} — skipped (not found)")

    if not section_contents:
        print("  No sections found. Run phase3_sectional.py first.")
        return

    # Extract data for charts and stats
    all_text = "\n".join(c for _, c in section_contents.values())
    stats = extract_stats(all_text)
    pull_quotes = extract_pull_quotes(all_text)
    ratings = load_play_store_ratings(data_dir)
    trends_regions = load_trends_regions(data_dir)
    market_numbers = parse_market_numbers(discovery)

    # Build chart JS
    market_chart = build_market_chart(market_numbers)
    ratings_chart = build_ratings_chart(ratings)
    trends_chart = build_trends_chart(trends_regions)

    # Build TOC
    toc_items = "".join(
        f'<li><a href="#section-{n}">{n}. {title}</a></li>'
        for n, (title, _) in section_contents.items()
    )

    # Build section HTML
    sections_html = []
    for n, (title, content) in section_contents.items():
        body = md_to_html(content)

        # Inject charts after specific sections
        extra = ""
        if n == 2 and market_chart:
            extra += market_chart
        if n == 3 and ratings_chart:
            extra += ratings_chart
        if n == 6 and trends_chart:
            extra += trends_chart

        # Inject a pull quote into section 4
        if n == 4 and pull_quotes:
            pq = build_pull_quote(pull_quotes[0])
            body = body + pq

        sections_html.append(f"""
<section id="section-{n}">
  <div class="section-header">
    <span class="section-num">{n:02d}</span>
    <h2>{title}</h2>
  </div>
  <div class="section-body">
    {body}
    {extra}
  </div>
</section>""")

    stat_boxes_html = build_stat_boxes(stats)
    timestamp = datetime.now().strftime("%B %d, %Y")
    source_count = sum(1 for p in data_dir.rglob("*.json") if p.exists()) if data_dir.exists() else 0

    # ── HTML template ──────────────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{topic} — Research Report</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root {{
    --blue: #0055cc; --blue-light: #e8f0fe; --green: #00a878;
    --orange: #f4a261; --red: #ef4444; --yellow: #f59e0b;
    --gray-50: #f8fafc; --gray-100: #f1f5f9; --gray-200: #e2e8f0;
    --gray-700: #334155; --gray-900: #0f172a;
    --font: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    --mono: 'SF Mono', 'Fira Code', monospace;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: var(--font); color: var(--gray-900); background: #fff;
    font-size: 15px; line-height: 1.75; }}

  /* ── Cover ── */
  .cover {{ background: var(--blue); color: #fff; padding: 56px 48px 48px;
    position: relative; overflow: hidden; }}
  .cover::after {{ content: ''; position: absolute; right: -60px; top: -60px;
    width: 320px; height: 320px; border-radius: 50%;
    background: rgba(255,255,255,0.06); }}
  .cover-label {{ font-size: 11px; font-weight: 700; letter-spacing: .12em;
    text-transform: uppercase; opacity: .7; margin-bottom: 16px; }}
  .cover h1 {{ font-size: 2.4em; font-weight: 800; line-height: 1.2;
    max-width: 640px; margin-bottom: 20px; }}
  .cover-meta {{ font-size: 13px; opacity: .75; display: flex; gap: 24px;
    flex-wrap: wrap; margin-top: 8px; }}
  .cover-meta span {{ display: flex; align-items: center; gap: 6px; }}

  /* ── Layout ── */
  .wrapper {{ display: grid; grid-template-columns: 240px 1fr;
    min-height: 100vh; }}
  .sidebar {{ position: sticky; top: 0; height: 100vh; overflow-y: auto;
    background: var(--gray-50); border-right: 1px solid var(--gray-200);
    padding: 32px 20px; }}
  .sidebar-title {{ font-size: 10px; font-weight: 700; letter-spacing: .1em;
    text-transform: uppercase; color: #94a3b8; margin-bottom: 16px; }}
  .sidebar nav ol {{ list-style: none; padding: 0; }}
  .sidebar nav li {{ margin-bottom: 4px; }}
  .sidebar nav a {{ display: block; padding: 7px 12px; border-radius: 6px;
    color: var(--gray-700); text-decoration: none; font-size: 13px;
    line-height: 1.4; transition: background .15s; }}
  .sidebar nav a:hover {{ background: var(--blue-light); color: var(--blue); }}
  .main {{ padding: 48px 56px; max-width: 860px; }}

  /* ── Stat grid ── */
  .stat-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 14px; margin: 32px 0; }}
  .stat-box {{ background: var(--blue-light); border-left: 4px solid var(--blue);
    border-radius: 8px; padding: 14px 16px; font-size: 13px;
    font-weight: 600; color: var(--blue); line-height: 1.4; }}

  /* ── Sections ── */
  section {{ margin-bottom: 56px; scroll-margin-top: 24px; }}
  .section-header {{ display: flex; align-items: center; gap: 16px;
    margin-bottom: 24px; padding-bottom: 14px;
    border-bottom: 2px solid var(--blue); }}
  .section-num {{ font-size: 11px; font-weight: 800; color: #fff;
    background: var(--blue); border-radius: 6px; padding: 4px 9px;
    letter-spacing: .05em; }}
  .section-header h2 {{ font-size: 1.35em; font-weight: 700; color: var(--gray-900); }}
  .section-body h3 {{ font-size: 1.05em; font-weight: 700; color: var(--blue);
    margin: 28px 0 10px; }}
  .section-body h4 {{ font-size: .95em; font-weight: 700; color: var(--gray-700);
    margin: 20px 0 8px; }}
  .section-body p {{ margin-bottom: 12px; color: #1e293b; }}
  .section-body ul, .section-body ol {{ padding-left: 20px; margin-bottom: 14px; }}
  .section-body li {{ margin-bottom: 6px; }}
  .section-body strong {{ color: var(--gray-900); }}
  .section-body em {{ color: #475569; }}
  .section-body hr {{ border: none; border-top: 1px solid var(--gray-200);
    margin: 28px 0; }}
  .section-body blockquote {{ border-left: 3px solid var(--blue);
    margin: 12px 0; padding: 4px 16px; color: #475569;
    background: var(--gray-50); border-radius: 0 6px 6px 0;
    font-size: 14px; }}
  .section-body code {{ background: var(--gray-100); padding: 2px 6px;
    border-radius: 4px; font-family: var(--mono); font-size: .88em; }}

  /* ── Tables ── */
  .table-wrap {{ overflow-x: auto; margin: 16px 0; border-radius: 8px;
    border: 1px solid var(--gray-200); }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13.5px; }}
  th {{ background: var(--blue); color: #fff; padding: 10px 14px;
    text-align: left; font-weight: 600; white-space: nowrap; }}
  td {{ padding: 9px 14px; border-bottom: 1px solid var(--gray-200);
    vertical-align: top; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:nth-child(even) {{ background: var(--gray-50); }}

  /* ── Charts ── */
  .chart-card {{ background: var(--gray-50); border: 1px solid var(--gray-200);
    border-radius: 10px; padding: 20px 24px; margin: 24px 0; }}
  .chart-card h4 {{ font-size: 13px; font-weight: 700; color: var(--gray-700);
    margin-bottom: 16px; }}
  .chart-wrap {{ position: relative; height: 240px; }}

  /* ── Pull quote ── */
  .pull-quote {{ background: #fff7ed; border-left: 4px solid var(--orange);
    border-radius: 0 10px 10px 0; padding: 16px 20px; margin: 24px 0;
    font-size: 14px; font-style: italic; color: #7c3a0d; line-height: 1.6; }}

  /* ── Print ── */
  @media print {{
    .sidebar {{ display: none; }}
    .wrapper {{ grid-template-columns: 1fr; }}
    .main {{ padding: 24px; max-width: 100%; }}
    .cover {{ padding: 32px; }}
    .chart-wrap {{ height: 200px; }}
  }}

  /* ── Mobile ── */
  @media (max-width: 768px) {{
    .wrapper {{ grid-template-columns: 1fr; }}
    .sidebar {{ display: none; }}
    .main {{ padding: 24px 20px; }}
    .cover {{ padding: 32px 24px; }}
    .cover h1 {{ font-size: 1.7em; }}
  }}
</style>
</head>
<body>

<div class="cover">
  <div class="cover-label">Market Research Report</div>
  <h1>{topic}</h1>
  <div class="cover-meta">
    <span>📅 {timestamp}</span>
    <span>📁 {len(section_contents)} sections</span>
    <span>🗂 {source_count} data files</span>
    <span>🔖 {slug}</span>
  </div>
</div>

<div class="wrapper">
  <aside class="sidebar">
    <div class="sidebar-title">Contents</div>
    <nav><ol>{toc_items}</ol></nav>
  </aside>

  <main class="main">
    {stat_boxes_html}
    {"".join(sections_html)}
  </main>
</div>

</body>
</html>"""

    # Save HTML
    html_path = config_file.parent / "report.html"
    html_path.write_text(html, encoding="utf-8")
    size_kb = html_path.stat().st_size // 1024
    print(f"\n  ✓ report.html → {html_path} ({size_kb} KB)")

    # Save plain markdown too
    md_parts = [f"# {topic} — Market Research Report\n"]
    md_parts.append(f"_Compiled: {timestamp}_\n\n---\n")
    for n, (title, content) in section_contents.items():
        md_parts.append(f"## {n}. {title}\n\n{content}\n\n---\n")
    md_path = config_file.parent / "report.md"
    md_path.write_text("\n".join(md_parts), encoding="utf-8")
    print(f"  ✓ report.md  → {md_path}")
    print(f"\n  Stats extracted: {len(stats)}")
    print(f"  Pull quotes:     {len(pull_quotes)}")
    print(f"  Charts built:    {sum([bool(market_chart), bool(ratings_chart), bool(trends_chart)])}")
    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: uv run python compile_rich.py research/<slug>/config.json")
        sys.exit(1)
    compile_report(sys.argv[1])
