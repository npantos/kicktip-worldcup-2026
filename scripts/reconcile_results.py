#!/usr/bin/env python3
"""Cross-check raw snapshots -> data/results/results.json.

Reconciliation status per match:
  - confirmed : >=2 independent sources report it and ALL agree on the scoreline
                (and penalties, if any)
  - provisional : exactly one source
  - disputed  : sources disagree -> left for a human/agent to resolve
                (add reconciliation.resolution_note and set status=confirmed,
                 manual=true; this script then leaves it untouched)

Only 'confirmed' results are scored and applied to Elo (enforced downstream via
store.confirmed_results()). Confirmed group/knockout matches also have their
fixture status flipped to 'completed' so predict.py stops re-baselining them.
"""
import glob
import os
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import store


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_snapshots():
    out = []
    for p in sorted(glob.glob(store.path("data/results/raw/*.json"))):
        out.append(store.load(os.path.relpath(p, store.ROOT)))
    return out


def score_key(r):
    pen = tuple(r["penalties"]) if r.get("penalties") else None
    return (r["home_goals"], r["away_goals"], pen)


def main():
    snaps = load_snapshots()
    fixtures = store.fixtures_by_id()

    reports = {}  # match_id -> {source: result}
    for s in snaps:
        src = s.get("source", "unknown")
        for r in s.get("results", []):
            reports.setdefault(r["match_id"], {})[src] = r

    existing = {x["match_id"]: x for x in store.results()}
    out = dict(existing)
    fixtures_data = store.load("data/fixtures.json")
    fx_by_id = {f["match_id"]: f for f in fixtures_data["fixtures"]}
    completed = 0

    for mid, by_source in reports.items():
        prev_rec = existing.get(mid, {}).get("reconciliation", {})
        if prev_rec.get("status") == "confirmed" and prev_rec.get("manual"):
            continue  # human-finalized; never overwrite

        keys = {score_key(r) for r in by_source.values()}
        sources = sorted(by_source)
        rep = by_source[sources[0]]
        f = fixtures.get(mid, {})
        rec = {"sources": sources, "n_sources": len(sources), "reconciled_at": now_utc()}
        if len(keys) > 1:
            rec["status"] = "disputed"
            rec["disagreement"] = {src: f"{r['home_goals']}-{r['away_goals']}"
                                   for src, r in by_source.items()}
            if prev_rec.get("resolution_note"):
                rec["resolution_note"] = prev_rec["resolution_note"]
        elif len(sources) >= 2:
            rec["status"] = "confirmed"
        else:
            rec["status"] = "provisional"

        entry = {
            "match_id": mid,
            "stage": f.get("stage"),
            "group": f.get("group"),
            "home": f.get("home"),
            "away": f.get("away"),
            "home_goals": rep["home_goals"],
            "away_goals": rep["away_goals"],
            "kickoff_utc": f.get("kickoff_utc"),
            "notes": sorted({r["note"] for r in by_source.values() if r.get("note")}),
            "reconciliation": rec,
        }
        if rep.get("penalties"):
            entry["penalties"] = rep["penalties"]
        out[mid] = entry

        if rec["status"] == "confirmed" and fx_by_id.get(mid, {}).get("status") == "scheduled":
            fx_by_id[mid]["status"] = "completed"
            completed += 1

    results_sorted = sorted(out.values(), key=lambda x: (x.get("kickoff_utc") or "", x["match_id"]))
    store.save("data/results/results.json", {"updated_at": now_utc(), "results": results_sorted})
    if completed:
        store.save("data/fixtures.json", fixtures_data)

    c = Counter(x["reconciliation"]["status"] for x in results_sorted)
    print(f"reconciled {len(results_sorted)} results: "
          + ", ".join(f"{k}={v}" for k, v in sorted(c.items())))
    for x in results_sorted:
        if x["reconciliation"]["status"] == "disputed":
            print(f"  DISPUTED {x['match_id']}: {x['reconciliation']['disagreement']}"
                  " -> resolve and set status=confirmed, manual=true")
    if completed:
        print(f"marked {completed} fixture(s) completed")


if __name__ == "__main__":
    main()
