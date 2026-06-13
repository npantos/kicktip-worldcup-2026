#!/usr/bin/env python3
"""Score confirmed results against every prediction track -> data/accuracy/ledger.json.

For each confirmed result we score, per track (model / adjusted / odds / external):
  - tendency_correct : argmax(probs) == actual outcome
  - brier            : sum (p_i - onehot_i)^2  (0 best, 2 worst)
  - logloss          : -ln P(actual outcome)
  - internal_pts     : 3 exact / 2 correct-goal-diff / 1 tendency / 0 miss
                       ("3/1/+1" metric; only tracks that carry a predicted score:
                        model.expected_score, adjusted.predicted_score, external)
And, separately, the REAL competition outcome of the bet that was placed:
  - kicktipp points under data/kicktipp_rules.json for the placed scoreline
  - kickgeist H/D/A pick correctness

Running per-track totals let us see which track is best calibrated over time.
"""
import glob
import math
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import store

OUTCOMES = ("home", "draw", "away")


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def match_day(kickoff_utc):
    dt = datetime.strptime(kickoff_utc, "%Y-%m-%dT%H:%M:%SZ")
    return (dt - timedelta(hours=7)).strftime("%Y-%m-%d")


def parse_score(s):
    if not s:
        return None
    for sep in ("-", ":"):
        if sep in s:
            a, b = s.split(sep)
            try:
                return int(a), int(b)
            except ValueError:
                return None
    return None


def outcome(gh, ga):
    return "home" if gh > ga else ("draw" if gh == ga else "away")


def internal_points(pred, act):
    """3 exact / 2 correct-goal-diff / 1 tendency / 0 miss."""
    ph, pa = pred
    ah, aa = act
    pt = (ph > pa) - (ph < pa)
    at = (ah > aa) - (ah < aa)
    if pt != at:
        return 0
    if (ph, pa) == (ah, aa):
        return 3
    if pt != 0 and (ph - pa) == (ah - aa):
        return 2
    return 1


def kicktipp_points(bet, act, rules):
    bh, ba = bet
    ah, aa = act
    win, draw = rules["points"]["win"], rules["points"]["draw"]
    bt = (bh > ba) - (bh < ba)
    at = (ah > aa) - (ah < aa)
    if bt != at:
        return 0
    if bt == 0:  # both draws
        return draw["exact"] if bh == ah else draw["tendency"]
    if (bh, ba) == (ah, aa):
        return win["exact"]
    if (bh - ba) == (ah - aa):
        return win["goal_diff"]
    return win["tendency"]


def load_predictions():
    by_id = {}
    for pf in sorted(glob.glob(store.path("data/predictions/*.json"))):
        day = store.load(os.path.relpath(pf, store.ROOT))
        for p in day["predictions"]:
            by_id[p["match_id"]] = p
    return by_id


def track_iter(pred):
    """Yield (name, probs|None, predicted_score|None)."""
    m = pred.get("model") or {}
    if m.get("p_home") is not None:
        yield "model", [m["p_home"], m["p_draw"], m["p_away"]], m.get("expected_score")
    a = pred.get("adjusted") or {}
    if a.get("p_home") is not None:
        yield "adjusted", [a["p_home"], a["p_draw"], a["p_away"]], a.get("predicted_score")
    o = pred.get("odds") or {}
    if o.get("p_home") is not None:
        yield "odds", [o["p_home"], o["p_draw"], o["p_away"]], None
    ext = (pred.get("external") or [])
    if ext:
        e = ext[-1]
        if e.get("p_home") is not None:
            yield "external", [e["p_home"], e["p_draw"], e["p_away"]], e.get("predicted_score")


def placed_bet(pred):
    """Most recent non-superseded kicktipp bet and latest kickgeist pick."""
    kt = kg = None
    for entry in pred.get("posted_to", []):
        if entry.get("platform") == "kicktipp" and "superseded_by" not in entry:
            kt = entry.get("bet")
        if entry.get("platform") == "kickgeist":
            kg = entry.get("pick")
    return kt, kg


def main():
    rules = store.load("data/kicktipp_rules.json")
    preds = load_predictions()
    confirmed = sorted(store.confirmed_results(),
                       key=lambda r: (r.get("kickoff_utc") or "", r["match_id"]))

    matches = []
    tt = {t: {"n": 0, "tendency_correct": 0, "internal_pts": 0, "n_scored": 0,
              "brier_sum": 0.0, "logloss_sum": 0.0} for t in
          ("model", "adjusted", "odds", "external")}
    kt_tot = {"n": 0, "points": 0}
    kg_tot = {"n": 0, "correct": 0}

    for r in confirmed:
        gh, ga = r["home_goals"], r["away_goals"]
        act = (gh, ga)
        act_out = outcome(gh, ga)
        oneh = [1.0 if o == act_out else 0.0 for o in OUTCOMES]
        pred = preds.get(r["match_id"])
        rec = {
            "match_id": r["match_id"],
            "date": match_day(r["kickoff_utc"]) if r.get("kickoff_utc") else None,
            "home": r["home"], "away": r["away"],
            "actual": f"{gh}-{ga}", "outcome": act_out,
            "tracks": {}, "bet": None,
        }
        if pred:
            for name, probs, pscore in track_iter(pred):
                idx = OUTCOMES.index(act_out)
                brier = sum((probs[i] - oneh[i]) ** 2 for i in range(3))
                logloss = -math.log(max(probs[idx], 1e-12))
                tendency = (max(range(3), key=lambda i: probs[i]) == idx)
                blk = {"probs": [round(x, 4) for x in probs],
                       "tendency_correct": tendency,
                       "brier": round(brier, 4), "logloss": round(logloss, 4)}
                ps = parse_score(pscore)
                blk["predicted_score"] = pscore
                blk["internal_pts"] = internal_points(ps, act) if ps else None
                rec["tracks"][name] = blk
                tt[name]["n"] += 1
                tt[name]["tendency_correct"] += int(tendency)
                tt[name]["brier_sum"] += brier
                tt[name]["logloss_sum"] += logloss
                if blk["internal_pts"] is not None:
                    tt[name]["internal_pts"] += blk["internal_pts"]
                    tt[name]["n_scored"] += 1

            kt_bet, kg_pick = placed_bet(pred)
            bet_block = {}
            kb = parse_score(kt_bet)
            if kb:
                pts = kicktipp_points(kb, act, rules)
                bet_block["kicktipp_bet"] = kt_bet
                bet_block["kicktipp_points"] = pts
                kt_tot["n"] += 1
                kt_tot["points"] += pts
            if kg_pick:
                correct = (kg_pick == act_out)
                bet_block["kickgeist_pick"] = kg_pick
                bet_block["kickgeist_correct"] = correct
                kg_tot["n"] += 1
                kg_tot["correct"] += int(correct)
            rec["bet"] = bet_block or None
        matches.append(rec)

    def finalize(d):
        d = dict(d)
        d["brier_avg"] = round(d["brier_sum"] / d["n"], 4) if d["n"] else None
        d["logloss_avg"] = round(d["logloss_sum"] / d["n"], 4) if d["n"] else None
        d["brier_sum"] = round(d["brier_sum"], 4)
        d["logloss_sum"] = round(d["logloss_sum"], 4)
        return d

    ledger = {
        "updated_at": now_utc(),
        "scoring": {
            "internal_metric": "3 exact / 2 correct-goal-diff / 1 tendency / 0 miss",
            "kicktipp_rules": "data/kicktipp_rules.json",
            "brier": "sum (p_i - onehot_i)^2, lower is better (0..2)",
        },
        "matches": matches,
        "totals": {
            "by_track": {t: finalize(v) for t, v in tt.items()},
            "kicktipp": dict(kt_tot, max_possible=kt_tot["n"] * rules["points"]["win"]["exact"]),
            "kickgeist": dict(kg_tot,
                              accuracy=round(kg_tot["correct"] / kg_tot["n"], 4) if kg_tot["n"] else None),
        },
    }
    store.save("data/accuracy/ledger.json", ledger)

    print(f"scored {len(matches)} confirmed match(es)")
    for t, v in ledger["totals"]["by_track"].items():
        if v["n"]:
            print(f"  {t:9s} n={v['n']} tendency={v['tendency_correct']}/{v['n']} "
                  f"internal={v['internal_pts']}pts brier_avg={v['brier_avg']}")
    print(f"  kicktipp {kt_tot['points']}/{ledger['totals']['kicktipp']['max_possible']} pts "
          f"over {kt_tot['n']} bets; kickgeist {kg_tot['correct']}/{kg_tot['n']} correct")


if __name__ == "__main__":
    main()
