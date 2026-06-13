#!/usr/bin/env python3
"""Apply confirmed results to Elo (append-only) -> data/elo/ratings_history.json.

Idempotent: only matches not already present in the history are applied, in
kickoff order. Penalty-shootout results must be stored as the 120' draw and
count as a draw for Elo (eloratings.net convention; handled by lib.elo).
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import store, elo


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main():
    init = store.load("data/elo/ratings_initial.json")
    hist = store.load("data/elo/ratings_history.json",
                      default={"initialized_from": init.get("snapshot_date"),
                               "k": elo.K_WORLD_CUP, "updates": [],
                               "current": dict(init["ratings"])})
    current = dict(hist["current"])
    applied = {u["match_id"] for u in hist["updates"]}
    fixtures = store.fixtures_by_id()

    pending = [r for r in store.confirmed_results() if r["match_id"] not in applied]
    pending.sort(key=lambda r: (r.get("kickoff_utc") or "", r["match_id"]))

    n = 0
    for r in pending:
        f = fixtures.get(r["match_id"], {})
        home, away = r["home"], r["away"]
        if home not in current or away not in current:
            print(f"skip {r['match_id']}: missing rating for {home}/{away}")
            continue
        bonus = elo.home_bonus(home, away, f.get("venue_country"))
        nh, na, det = elo.update(current[home], current[away],
                                 r["home_goals"], r["away_goals"], bonus=bonus)
        hist["updates"].append({
            "match_id": r["match_id"], "applied_at": now_utc(),
            "home": home, "away": away,
            "score": f"{r['home_goals']}-{r['away_goals']}",
            "home_adv_applied": bonus,
            "r_home_before": round(current[home], 1), "r_away_before": round(current[away], 1),
            "r_home_after": round(nh, 1), "r_away_after": round(na, 1),
            "delta_home": det["delta_home"], "g_multiplier": det["g"],
        })
        current[home], current[away] = nh, na
        n += 1
        print(f"{r['match_id']} {home} {r['home_goals']}-{r['away_goals']} {away}: "
              f"{home} {det['delta_home']:+.1f} -> {round(current[home], 1)}, "
              f"{away} {-det['delta_home']:+.1f} -> {round(na, 1)}")

    hist["current"] = {k: round(v, 1) for k, v in current.items()}
    hist["updated_at"] = now_utc()
    store.save("data/elo/ratings_history.json", hist)
    print(f"applied {n} new result(s); {len(hist['updates'])} total in history")


if __name__ == "__main__":
    main()
