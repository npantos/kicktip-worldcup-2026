#!/usr/bin/env python3
"""Expected-Kicktipp-points scoreline optimizer.

For each match in a day's prediction file, fits Poisson lambdas to each track's
outcome probabilities (the model track uses its stored lambdas directly), then
ranks candidate scorelines by expected points under data/kicktipp_rules.json.
The Kicktipp bet (runbook step 9) should be the EP-max scoreline on the adjusted
track, which may differ from the modal `predicted_score`.

Usage:
  optimal_score.py --date 2026-06-11
  optimal_score.py --date 2026-06-11 --top 5
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import store, poisson

MAX_CANDIDATE_GOALS = 6
LAMBDA_GRID_MAX = 4.0
LAMBDA_GRID_STEP = 0.025


def fit_lambdas(p_home, p_draw, p_away):
    """Grid-search (lambda_home, lambda_away) matching the outcome probabilities."""
    best = None
    steps = int(LAMBDA_GRID_MAX / LAMBDA_GRID_STEP)
    for i in range(1, steps + 1):
        lh = i * LAMBDA_GRID_STEP
        for j in range(1, steps + 1):
            la = j * LAMBDA_GRID_STEP
            ph, pd, pa = poisson.outcome_probs(poisson.score_matrix(lh, la))
            err = (ph - p_home) ** 2 + (pd - p_draw) ** 2 + (pa - p_away) ** 2
            if best is None or err < best[0]:
                best = (err, lh, la)
    return best[1], best[2]


def _points(h, a, pick_h, pick_a, rules):
    """Kicktipp points for betting pick vs an actual scoreline (h, a)."""
    win, draw = rules["points"]["win"], rules["points"]["draw"]
    same_tendency = (
        (h > a and pick_h > pick_a)
        or (h == a and pick_h == pick_a)
        or (h < a and pick_h < pick_a)
    )
    if not same_tendency:
        return 0.0
    if h == pick_h and a == pick_a:
        return (draw if pick_h == pick_a else win)["exact"]
    if pick_h == pick_a:
        return draw["tendency"]  # draws have no goal-diff tier
    if h - a == pick_h - pick_a:
        return win["goal_diff"]
    return win["tendency"]


def expected_points(matrix, pick_h, pick_a, rules, knockout=False):
    """Expected Kicktipp points for betting pick_h:pick_a, given a scoreline matrix.

    knockout=True applies this community's 'after penalties' rule: a level
    scoreline (h, h) is never the final applied result -- it resolves to a
    one-goal win for the shootout winner (50/50), i.e. (h+1, h) or (h, h+1)."""
    ep = 0.0
    for h, row in enumerate(matrix):
        for a, p in enumerate(row):
            if knockout and h == a:
                ep += 0.5 * p * _points(h + 1, a, pick_h, pick_a, rules)
                ep += 0.5 * p * _points(h, a + 1, pick_h, pick_a, rules)
            else:
                ep += p * _points(h, a, pick_h, pick_a, rules)
    return ep


def rank_scorelines(matrix, rules, knockout=False):
    rows = []
    for h in range(MAX_CANDIDATE_GOALS + 1):
        for a in range(MAX_CANDIDATE_GOALS + 1):
            rows.append((expected_points(matrix, h, a, rules, knockout), h, a))
    rows.sort(key=lambda r: -r[0])
    return rows


def track_probs(pred):
    """Yield (track_name, p_home, p_draw, p_away, lambdas_or_None), adjusted first."""
    adj = pred.get("adjusted") or {}
    if adj.get("p_home") is not None:
        yield "adjusted", adj["p_home"], adj["p_draw"], adj["p_away"], None
    model = pred.get("model") or {}
    if model.get("p_home") is not None:
        lams = (model.get("lambda_home"), model.get("lambda_away"))
        yield "model", model["p_home"], model["p_draw"], model["p_away"], lams
    odds = pred.get("odds") or {}
    if odds.get("p_home") is not None:
        yield "odds", odds["p_home"], odds["p_draw"], odds["p_away"], None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="YYYY-MM-DD prediction file to optimize")
    ap.add_argument("--top", type=int, default=4, help="scorelines to show per track")
    args = ap.parse_args()

    day = store.load(f"data/predictions/{args.date}.json")
    rules = store.load("data/kicktipp_rules.json")
    fixtures = store.fixtures_by_id()

    pts = rules["points"]
    print(f"Kicktipp points: win {pts['win']['tendency']}/{pts['win']['goal_diff']}/"
          f"{pts['win']['exact']}, draw {pts['draw']['tendency']}/{pts['draw']['exact']}"
          f" (effective {rules['effective_from']})")

    for pred in day["predictions"]:
        mid = pred["match_id"]
        fx = fixtures.get(mid, {})
        ko = fx.get("stage") not in (None, "group")
        label = f"{fx.get('home', '?')} vs {fx.get('away', '?')}" + ("  [KO: after-pens]" if ko else "")
        print(f"\n{mid} {label}")
        for name, ph, pd, pa, lams in track_probs(pred):
            if lams and lams[0] is not None:
                lh, la = lams
            else:
                lh, la = fit_lambdas(ph, pd, pa)
            matrix = poisson.score_matrix(lh, la)
            ranked = rank_scorelines(matrix, rules, ko)[: args.top]
            picks = "  ".join(f"{h}:{a}={ep:.3f}" for ep, h, a in ranked)
            print(f"  {name:9s} ({ph:.2f}/{pd:.2f}/{pa:.2f}, lh={lh:.2f} la={la:.2f})  {picks}")
        bet = next((p["bet"] for p in reversed(pred.get("posted_to", []))
                    if p.get("platform") == "kicktipp" and "superseded_by" not in p), None)
        if bet:
            print(f"  current kicktipp bet: {bet}")


if __name__ == "__main__":
    main()
