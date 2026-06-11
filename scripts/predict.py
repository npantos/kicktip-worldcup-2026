#!/usr/bin/env python3
"""Model-baseline predictions + odds/external ingestion.

A "match day" is the calendar date in UTC-7 (the westernmost venue timezone),
so late local kickoffs that cross midnight UTC stay on their local day.

Usage:
  predict.py --date 2026-06-11                 # write model baselines
  predict.py --date D --set-odds '[{"match_id":"M001","source":"bet365 via wc26-mcp",
                                    "odds":[1.55,4.2,6.5]}]'
  predict.py --date D --set-external '[{"match_id":"M001","source":"api-football",
                                        "p_home":0.6,"p_draw":0.25,"p_away":0.15,
                                        "predicted_score":"2-0"}]'
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import store, elo, poisson, odds as oddslib


def match_day(kickoff_utc):
    dt = datetime.strptime(kickoff_utc, "%Y-%m-%dT%H:%M:%SZ")
    return (dt - timedelta(hours=7)).strftime("%Y-%m-%d")


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_locked(pred):
    return pred.get("locked_at") and pred["locked_at"] <= now_utc()


def round_probs(ph, pd, pa, places=4):
    """Round a probability triple so the stored values still sum to exactly 1.

    Independent rounding can drift the sum by ~1e-4, which validate.py rejects;
    the residual is folded into the largest component."""
    vals = [round(v, places) for v in (ph, pd, pa)]
    i = vals.index(max(vals))
    vals[i] = round(vals[i] + (1.0 - sum(vals)), places)
    return vals


def model_block(fixture, ratings):
    home, away = fixture["home"], fixture["away"]
    if home is None or away is None:
        return None  # knockout slot not resolved yet
    bonus = elo.home_bonus(home, away, fixture.get("venue_country"))
    rh, ra = ratings[home], ratings[away]
    lh, la = elo.lambdas(rh, ra, bonus)
    matrix = poisson.score_matrix(lh, la)
    ph, pd, pa = poisson.outcome_probs(matrix)
    mh, ma = poisson.modal_score(matrix, tiebreak_home=lh >= la)
    rph, rpd, rpa = round_probs(ph, pd, pa)
    blk = {
        "elo_home": round(rh, 1), "elo_away": round(ra, 1),
        "home_adv_applied": bonus,
        "lambda_home": round(lh, 3), "lambda_away": round(la, 3),
        "p_home": rph, "p_draw": rpd, "p_away": rpa,
        "expected_score": f"{mh}-{ma}",
        "p_home_advance": None,
    }
    if fixture["stage"] != "group":
        # advance prob: win in 90' + half of draws (ET modeled ~even tilt, pens 50/50)
        blk["p_home_advance"] = round(ph + pd * (0.5 + (ph - pa) * 0.2), 4)
    return blk


def load_day(date):
    rel = f"data/predictions/{date}.json"
    return rel, store.load(rel, default={"match_date": date, "predictions": []})


def cmd_baseline(date):
    ratings = store.current_elo()
    fixtures = [f for f in store.fixtures()
                if match_day(f["kickoff_utc"]) == date and f["status"] == "scheduled"]
    if not fixtures:
        print(f"no scheduled fixtures on match day {date}")
        return
    rel, day = load_day(date)
    by_id = {p["match_id"]: p for p in day["predictions"]}
    for f in fixtures:
        blk = model_block(f, ratings)
        if blk is None:
            print(f"skip {f['match_id']}: knockout slot unresolved")
            continue
        p = by_id.get(f["match_id"])
        if p is None:
            p = {"match_id": f["match_id"], "created_at": now_utc(),
                 "locked_at": None, "model": blk, "adjusted": None,
                 "odds": None, "external": [], "posted_to": []}
            day["predictions"].append(p)
            by_id[f["match_id"]] = p
        elif is_locked(p):
            print(f"skip {f['match_id']}: locked")
            continue
        else:
            p["model"] = blk
        print(f"{f['match_id']} {f['home']}-{f['away']}: "
              f"{blk['p_home']:.0%}/{blk['p_draw']:.0%}/{blk['p_away']:.0%} "
              f"-> {blk['expected_score']}")
    store.save(rel, day)
    print(f"wrote {rel}")


def cmd_set_odds(date, payload):
    rel, day = load_day(date)
    by_id = {p["match_id"]: p for p in day["predictions"]}
    for item in json.loads(payload):
        p = by_id.get(item["match_id"])
        if p is None:
            print(f"skip {item['match_id']}: no prediction entry (run baseline first)")
            continue
        if is_locked(p):
            print(f"skip {item['match_id']}: locked")
            continue
        oh, od, oa = item["odds"]
        ph, pd, pa = oddslib.implied_probs(oh, od, oa)
        rph, rpd, rpa = round_probs(ph, pd, pa)
        p["odds"] = {
            "source": item.get("source", "unknown"),
            "decimal_odds": [oh, od, oa],
            "overround": round(oddslib.overround(oh, od, oa), 4),
            "p_home": rph, "p_draw": rpd, "p_away": rpa,
            "fetched_at": now_utc(),
        }
        print(f"{item['match_id']}: market {ph:.0%}/{pd:.0%}/{pa:.0%} "
              f"(overround {p['odds']['overround']:.1%})")
    store.save(rel, day)


def cmd_set_external(date, payload):
    rel, day = load_day(date)
    by_id = {p["match_id"]: p for p in day["predictions"]}
    for item in json.loads(payload):
        p = by_id.get(item["match_id"])
        if p is None or is_locked(p):
            print(f"skip {item['match_id']}: missing or locked")
            continue
        entry = {k: item[k] for k in
                 ("source", "p_home", "p_draw", "p_away") if k in item}
        entry["predicted_score"] = item.get("predicted_score")
        entry["fetched_at"] = now_utc()
        p["external"] = [e for e in p.get("external", [])
                         if e.get("source") != entry.get("source")] + [entry]
        print(f"{item['match_id']}: external {entry.get('source')} added")
    store.save(rel, day)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True,
                    help="match day YYYY-MM-DD (calendar date in UTC-7)")
    ap.add_argument("--set-odds", metavar="JSON")
    ap.add_argument("--set-external", metavar="JSON")
    args = ap.parse_args()
    if args.set_odds:
        cmd_set_odds(args.date, args.set_odds)
    elif args.set_external:
        cmd_set_external(args.date, args.set_external)
    else:
        cmd_baseline(args.date)


if __name__ == "__main__":
    main()
