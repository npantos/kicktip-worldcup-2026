#!/usr/bin/env python3
"""Sanity-check all data files. Exit 1 on any failure."""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import store

ERRORS = []


def check(cond, msg):
    if not cond:
        ERRORS.append(msg)


def main():
    teams = store.teams()
    check(len(teams) == 48, f"expected 48 teams, got {len(teams)}")
    groups = {}
    for t in teams.values():
        groups.setdefault(t["group"], []).append(t["id"])
        check(isinstance(t["elo_initial"], int), f"{t['id']}: elo_initial not int")
    check(sorted(groups) == list("ABCDEFGHIJKL"), f"groups: {sorted(groups)}")
    for g, ids in groups.items():
        check(len(ids) == 4, f"group {g} has {len(ids)} teams")

    fixtures = store.fixtures()
    check(len(fixtures) == 104, f"expected 104 fixtures, got {len(fixtures)}")
    ids = [f["match_id"] for f in fixtures]
    check(len(set(ids)) == len(ids), "duplicate match_ids")
    group_fx = [f for f in fixtures if f["stage"] == "group"]
    ko_fx = [f for f in fixtures if f["stage"] != "group"]
    check(len(group_fx) == 72 and len(ko_fx) == 32,
          f"stage split {len(group_fx)}+{len(ko_fx)} != 72+32")
    appearances = {}
    for f in group_fx:
        for side in ("home", "away"):
            check(f[side] in teams, f"{f['match_id']}: unknown team {f[side]}")
            appearances[f[side]] = appearances.get(f[side], 0) + 1
        check(teams[f["home"]]["group"] == f["group"] == teams[f["away"]]["group"],
              f"{f['match_id']}: group mismatch")
    for tid, n in appearances.items():
        check(n == 3, f"{tid} has {n} group matches")
    for f in ko_fx:
        if f["home"] is None:
            check(f["home_slot"] and f["away_slot"], f"{f['match_id']}: missing slots")

    bt = store.load("data/bracket_template.json")
    direct = [s for r in bt["r32_slots"] for s in (r["home_slot"], r["away_slot"])
              if s[0] in "12"]
    want = sorted(n + g for n in "12" for g in "ABCDEFGHIJKL")
    check(sorted(direct) == want, "R32 winner/runner-up slots incomplete")
    check(len(bt["third_slot_sets"]) == 8, "expected 8 third-place R32 slots")

    init = store.load("data/elo/ratings_initial.json")
    check(set(init["ratings"]) == set(teams), "ratings_initial team mismatch")

    # results referential integrity
    fx_ids = set(ids)
    for r in store.results():
        check(r["match_id"] in fx_ids, f"result for unknown match {r['match_id']}")
        st = r["reconciliation"]["status"]
        check(st in ("confirmed", "provisional", "disputed"),
              f"{r['match_id']}: bad status {st}")

    # predictions: probability sums and lock integrity
    for pf in sorted(glob.glob(store.path("data/predictions/*.json"))):
        day = store.load(os.path.relpath(pf, store.ROOT))
        for p in day["predictions"]:
            check(p["match_id"] in fx_ids,
                  f"prediction for unknown match {p['match_id']}")
            for track in ("model", "adjusted", "odds"):
                blk = p.get(track)
                if blk:
                    s = blk["p_home"] + blk["p_draw"] + blk["p_away"]
                    check(abs(s - 1.0) < 1e-6,
                          f"{p['match_id']}.{track}: probs sum {s:.4f}")

    if ERRORS:
        print(f"FAIL ({len(ERRORS)} errors)")
        for e in ERRORS:
            print(" -", e)
        sys.exit(1)
    print("validate.py: all checks passed")


if __name__ == "__main__":
    main()
