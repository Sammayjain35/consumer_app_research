"""
Google Trends Research Tool
Keyword interest over time, regional breakdowns, related queries.

Usage:
    uv run python tools/google_trends.py --keywords "ramayan app,mahabharata app" --geo IN
    uv run python tools/google_trends.py --keywords "kids homework help" --geo IN --timeframe "today 12-m"
    uv run python tools/google_trends.py --keywords "astrology,numerology" --geo IN --compare

Flags:
    --keywords   Comma-separated keywords (max 5)
    --geo        Country code (default: IN for India)
    --timeframe  Timeframe string (default: "today 12-m")
                 Options: "today 1-m", "today 3-m", "today 12-m", "today 5-y", "all"
    --compare    Compare keywords against each other
    --out        Output directory (default: data/google_trends)
"""
import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from pytrends.request import TrendReq


def _get_trends(keywords: list[str], geo: str = "IN", timeframe: str = "today 12-m") -> TrendReq:
    pt = TrendReq(hl="en-US", tz=330)  # tz=330 for India
    pt.build_payload(keywords, cat=0, timeframe=timeframe, geo=geo, gprop="")
    return pt


# ── Interest over time ────────────────────────────────────────────────────────

def interest_over_time(keywords: list[str], geo: str = "IN", timeframe: str = "today 12-m") -> dict:
    print(f"\n📈 Interest over time: {keywords}")
    pt = _get_trends(keywords, geo, timeframe)
    try:
        df = pt.interest_over_time()
        if df.empty:
            print("  ⚠️  No data returned")
            return {}
        result = {}
        for kw in keywords:
            if kw in df.columns:
                series = df[kw]
                result[kw] = {
                    "avg_interest":  round(float(series.mean()), 1),
                    "max_interest":  int(series.max()),
                    "min_interest":  int(series.min()),
                    "trend":         "rising" if series.iloc[-1] > series.iloc[0] else "falling",
                    "last_value":    int(series.iloc[-1]),
                    "first_value":   int(series.iloc[0]),
                    "time_series":   {str(k): int(v) for k, v in series.items()},
                }
                print(f"  {kw}: avg={result[kw]['avg_interest']} | max={result[kw]['max_interest']} | trend={result[kw]['trend']}")
        return result
    except Exception as e:
        print(f"  ⚠️  Error: {e}")
        return {}


# ── Regional interest ─────────────────────────────────────────────────────────

def interest_by_region(keywords: list[str], geo: str = "IN",
                       timeframe: str = "today 12-m", resolution: str = "REGION") -> dict:
    print(f"\n🗺️  Regional interest (resolution={resolution})")
    pt = _get_trends(keywords, geo, timeframe)
    try:
        df = pt.interest_by_region(resolution=resolution, inc_low_vol=True, inc_geo_code=True)
        if df.empty:
            return {}
        result = {}
        for kw in keywords:
            if kw in df.columns:
                top = df[kw].sort_values(ascending=False).head(15)
                result[kw] = {row_idx: int(val) for row_idx, val in top.items()}
                print(f"  {kw} top regions: {list(result[kw].keys())[:5]}")
        return result
    except Exception as e:
        print(f"  ⚠️  Error: {e}")
        return {}


# ── Related queries ───────────────────────────────────────────────────────────

def related_queries(keywords: list[str], geo: str = "IN", timeframe: str = "today 12-m") -> dict:
    print(f"\n🔗 Related queries")
    pt = _get_trends(keywords, geo, timeframe)
    try:
        data = pt.related_queries()
        result = {}
        for kw in keywords:
            kw_data = data.get(kw, {})
            top_df   = kw_data.get("top")
            rising_df = kw_data.get("rising")
            result[kw] = {
                "top":    top_df.to_dict("records") if top_df is not None and not top_df.empty else [],
                "rising": rising_df.to_dict("records") if rising_df is not None and not rising_df.empty else [],
            }
            print(f"  {kw}: {len(result[kw]['top'])} top | {len(result[kw]['rising'])} rising")
        return result
    except Exception as e:
        print(f"  ⚠️  Error: {e}")
        return {}


# ── Save ──────────────────────────────────────────────────────────────────────

def save(name: str, data: dict, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{name}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    print(f"\n✅ Saved → {path}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Google Trends research tool")
    parser.add_argument("--keywords",  required=True, help="Comma-separated keywords (max 5)")
    parser.add_argument("--geo",       default="IN")
    parser.add_argument("--timeframe", default="today 12-m",
                        help='e.g. "today 12-m", "today 5-y", "all"')
    parser.add_argument("--compare",   action="store_true", help="Side-by-side comparison mode")
    parser.add_argument("--out",       default="data/google_trends")
    args = parser.parse_args()

    keywords = [k.strip() for k in args.keywords.split(",")][:5]
    print(f"Keywords: {keywords} | Geo: {args.geo} | Timeframe: {args.timeframe}")

    out_data = {
        "keywords":  keywords,
        "geo":       args.geo,
        "timeframe": args.timeframe,
        "fetched_at": datetime.now().isoformat(),
    }

    out_data["interest_over_time"] = interest_over_time(keywords, args.geo, args.timeframe)
    time.sleep(1)
    out_data["interest_by_region"] = interest_by_region(keywords, args.geo, args.timeframe)
    time.sleep(1)
    out_data["related_queries"]    = related_queries(keywords, args.geo, args.timeframe)

    safe = "_".join(keywords)[:40].replace(" ", "_")
    save(safe, out_data, Path(args.out))


if __name__ == "__main__":
    main()
