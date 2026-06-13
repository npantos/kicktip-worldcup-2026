#!/usr/bin/env python3
"""Fetch match results into write-once raw snapshots under data/results/raw/.

No automated results API is configured in this repo, so the supported path is
--manual: pass a JSON payload assembled from web search (FIFA/BBC/ESPN) or the
wc26-mcp tools, with source attribution. Each call writes ONE immutable snapshot
(never overwritten); reconcile_results.py later cross-checks the snapshots and
promotes a match to 'confirmed' once >=2 independent sources agree.

Usage:
  fetch_results.py --manual '{"source":"ESPN","urls":["https://..."],
      "results":[{"match_id":"M001","home_goals":2,"away_goals":0,"note":"..."}]}'
  fetch_results.py --date 2026-06-12      # no API configured -> prints guidance
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import store


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:40] or "src"


def write_snapshot(payload):
    src = payload.get("source") or "unknown"
    fetched = payload.get("fetched_at") or now_utc()
    results = payload.get("results") or []
    if not results:
        raise SystemExit("payload has no results")
    fixtures = store.fixtures_by_id()
    for r in results:
        mid = r.get("match_id")
        if mid not in fixtures:
            raise SystemExit(f"unknown match_id {mid!r}")
        if not isinstance(r.get("home_goals"), int) or not isinstance(r.get("away_goals"), int):
            raise SystemExit(f"{mid}: home_goals/away_goals must be integers")
        if r.get("penalties") is not None:
            p = r["penalties"]
            if not (isinstance(p, list) and len(p) == 2 and all(isinstance(x, int) for x in p)):
                raise SystemExit(f"{mid}: penalties must be [int, int]")
    snap = {
        "fetched_at": fetched,
        "source": src,
        "urls": payload.get("urls", []),
        "method": payload.get("method", "manual"),
        "results": results,
    }
    name = f"{fetched.replace(':', '').replace('-', '')}_{slug(src)}.json"
    rel = f"data/results/raw/{name}"
    if os.path.exists(store.path(rel)):
        raise SystemExit(f"snapshot {rel} already exists (raw snapshots are write-once)")
    store.save(rel, snap)
    print(f"wrote {rel} ({len(results)} results from '{src}')")
    return rel


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manual", metavar="JSON", help="results payload with source attribution")
    ap.add_argument("--date", help="match day to fetch (no API configured -> guidance)")
    args = ap.parse_args()
    if args.manual:
        write_snapshot(json.loads(args.manual))
    elif args.date:
        print(f"no automated results API is configured; supply final scores for {args.date} "
              "via --manual with source attribution (web search FIFA/BBC/ESPN, or wc26-mcp).")
    else:
        ap.error("one of --manual or --date is required")


if __name__ == "__main__":
    main()
