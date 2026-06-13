#!/usr/bin/env python3
"""League-aware bet strategy: turn EP-max into win-the-league-max.

optimal_score.py maximizes EXPECTED points per match. To finish 1st in the
Kicktipp league you instead want to maximize P(rank 1) given your standing,
which implies a position-dependent variance preference:

  ACCUMULATE  (default; long season left OR small deficit): bet EP-max.
  LEAN_VARIANCE / CATCH_UP (trailing, late): variance-SEEKING ->
              maximize EP + k*sigma, preferring exact-score upside that can
              leapfrog the packed field.
  PROTECT     (leading, late): variance-AVERSE -> maximize EP - k*sigma,
              mirror safe chalk so a single swing can't be caught.

k scales with urgency = deficit / (remaining_group_matches * max_pts). Early in
a long season urgency ~ 0, so this collapses to plain EP-max -- which is correct:
with ~70 group games left, calibration compounds and -EV variance only hurts.
The tilt only bites near the end. Reads data/league/standings.json (refresh it
from the kicktipp MCP each cycle: get_overview / get_leaderboard).

Usage:
  contest_strategy.py                    # report current mode + urgency
  contest_strategy.py --date 2026-06-13  # EP-max vs contest pick per match
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import store, poisson
from optimal_score import fit_lambdas, MAX_CANDIDATE_GOALS

ACCUMULATE_URGENCY = 0.08   # below this -> pure EP-max
CATCHUP_URGENCY = 0.20      # above this -> full variance-seeking
K_SCALE = 6.0               # urgency -> variance weight
MAX_PTS = 6                 # exact-score points (the attainable max per match)


def points(bet, outcome, rules):
    bh, ba = bet
    h, a = outcome
    win, draw = rules["points"]["win"], rules["points"]["draw"]
    bt = (bh > ba) - (bh < ba)
    at = (h > a) - (h < a)
    if bt != at:
        return 0
    if bt == 0:
        return draw["exact"] if bh == h else draw["tendency"]
    if (bh, ba) == (h, a):
        return win["exact"]
    if (bh - ba) == (h - a):
        return win["goal_diff"]
    return win["tendency"]


def ep_sigma(matrix, bet, rules):
    e = e2 = 0.0
    for h, row in enumerate(matrix):
        for a, p in enumerate(row):
            pts = points(bet, (h, a), rules)
            e += p * pts
            e2 += p * pts * pts
    return e, max(0.0, e2 - e * e) ** 0.5


def remaining_matches():
    fx = store.fixtures()
    rem = [f for f in fx if f.get("status") == "scheduled"]
    grp = [f for f in rem if f["stage"] == "group"]
    return len(rem), len(grp)


def compute_mode(standings):
    deficit = standings.get("deficit_to_leader", 0)
    rem_total, rem_grp = remaining_matches()
    pool = max(1, rem_grp) * MAX_PTS
    urgency = deficit / pool if deficit > 0 else 0.0
    leading = deficit <= 0
    if leading and rem_grp <= 6:
        mode, k = "PROTECT", min(1.5, K_SCALE * 0.05)
    elif urgency < ACCUMULATE_URGENCY:
        mode, k = "ACCUMULATE", 0.0
    elif urgency < CATCHUP_URGENCY:
        mode, k = "LEAN_VARIANCE", K_SCALE * urgency
    else:
        mode, k = "CATCH_UP", min(2.5, K_SCALE * urgency)
    return {"mode": mode, "urgency": round(urgency, 4), "k": round(k, 3),
            "deficit": deficit, "remaining_group": rem_grp,
            "remaining_total": rem_total, "points_pool_group": pool}


def objective(ep, sigma, mode, k):
    if mode == "PROTECT":
        return ep - k * sigma
    if mode in ("LEAN_VARIANCE", "CATCH_UP"):
        return ep + k * sigma
    return ep


def best_bets(matrix, rules, mode, k, top=4):
    rows = []
    for h in range(MAX_CANDIDATE_GOALS + 1):
        for a in range(MAX_CANDIDATE_GOALS + 1):
            ep, sig = ep_sigma(matrix, (h, a), rules)
            rows.append((objective(ep, sig, mode, k), ep, sig, h, a))
    rows.sort(key=lambda r: -r[0])
    return rows[:top]


def track_probs(pred):
    adj = pred.get("adjusted") or {}
    if adj.get("p_home") is not None:
        return "adjusted", adj["p_home"], adj["p_draw"], adj["p_away"]
    od = pred.get("odds") or {}
    if od.get("p_home") is not None:
        return "odds", od["p_home"], od["p_draw"], od["p_away"]
    m = pred.get("model") or {}
    return "model", m.get("p_home"), m.get("p_draw"), m.get("p_away")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="prediction file to evaluate")
    ap.add_argument("--top", type=int, default=4)
    args = ap.parse_args()

    standings = store.load("data/league/standings.json")
    rules = store.load("data/kicktipp_rules.json")
    st = compute_mode(standings)
    me = standings.get("me", {})
    lead = standings.get("leader", {})
    lead_name = "/".join(lead.get("names", [])) or lead.get("name", "?")

    print(f"League: {me.get('name')} rank {me.get('rank')}/{standings.get('field_size')}, "
          f"{me.get('points')} pts, {st['deficit']} behind leader ({lead_name} {lead.get('points')}).")
    print(f"Remaining group matches: {st['remaining_group']} "
          f"(pool {st['points_pool_group']} pts). Urgency {st['urgency']:.3f} "
          f"-> MODE = {st['mode']} (variance weight k={st['k']}).")
    if st["mode"] == "ACCUMULATE":
        print("=> Bet EP-max. Variance plays would be -EV with this much season left; "
              "edge must come from calibration / exact scores, not gambles.")
    elif st["mode"] == "PROTECT":
        print("=> Variance-averse: mirror safe chalk to lock the lead.")
    else:
        print("=> Variance-seeking: prefer exact-score upside to leapfrog the packed field.")

    if not args.date:
        return
    day = store.load(f"data/predictions/{args.date}.json")
    fixtures = store.fixtures_by_id()
    for pred in day["predictions"]:
        mid = pred["match_id"]
        fx = fixtures.get(mid, {})
        name, ph, pd, pa = track_probs(pred)
        if ph is None:
            continue
        lh, la = fit_lambdas(ph, pd, pa)
        matrix = poisson.score_matrix(lh, la)
        epmax = best_bets(matrix, rules, "ACCUMULATE", 0.0, 1)[0]
        contest = best_bets(matrix, rules, st["mode"], st["k"], args.top)
        cb = contest[0]
        differs = "" if (cb[3], cb[4]) == (epmax[3], epmax[4]) else "   <-- differs from EP-max"
        print(f"\n{mid} {fx.get('home')} vs {fx.get('away')} [{name}]")
        print(f"  EP-max : {epmax[3]}:{epmax[4]}  (EP {epmax[1]:.3f}, sigma {epmax[2]:.2f})")
        print(f"  contest: {cb[3]}:{cb[4]}  (EP {cb[1]:.3f}, sigma {cb[2]:.2f}, obj {cb[0]:.3f}){differs}")
        alts = "  ".join(f"{h}:{a}[EP{ep:.2f} s{sig:.2f}]" for _, ep, sig, h, a in contest)
        print(f"  ranked : {alts}")


if __name__ == "__main__":
    main()
