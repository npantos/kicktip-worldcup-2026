#!/usr/bin/env python3
"""Daily digest -> reports/daily/YYYY-MM-DD.md.

Summarizes one match day: picks across tracks, confirmed results + points,
Elo movement, the latest simulation snapshot, and open status/gaps.
"""
import argparse
import glob
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import store, poisson
from optimal_score import fit_lambdas, rank_scorelines


def match_day(kickoff_utc):
    dt = datetime.strptime(kickoff_utc, "%Y-%m-%dT%H:%M:%SZ")
    return (dt - timedelta(hours=7)).strftime("%Y-%m-%d")


def pct(x):
    return f"{x:.0%}" if isinstance(x, (int, float)) else "—"


def placed_bet(pred):
    """The active (non-superseded) Kicktipp bet recorded on a prediction, or None."""
    for e in reversed(pred.get("posted_to", [])):
        if e.get("platform") == "kicktipp" and not e.get("superseded_by"):
            return e.get("bet")
    return None


def epmax_bet(blk, rules, knockout=False):
    """EP-max scoreline + its expected Kicktipp points for one track block.

    Uses the model track's stored lambdas; for tracks without lambdas (adjusted,
    odds) it fits them to the outcome probabilities, exactly like optimal_score.py.
    This is the points-maximizing bet, which may differ from the modal scoreline."""
    lh, la = blk.get("lambda_home"), blk.get("lambda_away")
    if lh is None or la is None:
        lh, la = fit_lambdas(blk["p_home"], blk["p_draw"], blk["p_away"])
    ep, h, a = rank_scorelines(poisson.score_matrix(lh, la), rules, knockout)[0]
    return f"{h}:{a}", ep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="match day YYYY-MM-DD")
    args = ap.parse_args()
    date = args.date

    teams = store.teams()
    fixtures = store.fixtures_by_id()
    day = store.load(f"data/predictions/{date}.json", default={"predictions": []})
    results = {r["match_id"]: r for r in store.results()}
    ledger = store.load("data/accuracy/ledger.json", default={"matches": [], "totals": {}})
    ledger_by_id = {m["match_id"]: m for m in ledger.get("matches", [])}
    hist = store.load("data/elo/ratings_history.json", default={"updates": []})
    rules = store.load("data/kicktipp_rules.json")

    def name(tid):
        return teams[tid]["name"] if tid in teams else (tid or "?")

    L = [f"# Daily Digest — {date}", ""]

    L.append("## Matches & picks")
    L.append("")
    if not day["predictions"]:
        L.append("_No predictions on this match day._")
        L.append("")
    for p in day["predictions"]:
        mid = p["match_id"]
        fx = fixtures.get(mid, {})
        ko = fx.get("kickoff_utc", "")
        is_ko = fx.get("stage") not in (None, "group")
        L.append(f"### {mid} · {name(fx.get('home'))} vs {name(fx.get('away'))}"
                 f" — {ko} ({'KO: after-pens' if is_ko else 'Group ' + str(fx.get('group', '?'))})")
        L.append("")
        L.append("| Track | Home | Draw | Away | Likely score | EP-max bet (pts) |")
        L.append("|---|---|---|---|---|---|")
        for tname, key in (("Model", "model"), ("Adjusted", "adjusted"),
                           ("Odds", "odds")):
            blk = p.get(key)
            if blk and blk.get("p_home") is not None:
                sc = blk.get("predicted_score") or blk.get("expected_score") or "—"
                bet_sc, ep = epmax_bet(blk, rules, is_ko)
                star = " **(pick)**" if key == "adjusted" else ""
                L.append(f"| {tname}{star} | {pct(blk['p_home'])} | {pct(blk['p_draw'])} "
                         f"| {pct(blk['p_away'])} | {sc} | {bet_sc} ({ep:.2f}) |")
        r = results.get(mid)
        if r:
            st = r["reconciliation"]["status"]
            L.append(f"| **Actual** | | | | **{r['home_goals']}-{r['away_goals']}** ({st}) | |")
        L.append("")
        bet = placed_bet(p)
        led = ledger_by_id.get(mid)
        scored = bool(led and led.get("bet") and "kicktipp_points" in led["bet"])
        if bet and not scored:
            L.append(f"**Kicktipp bet placed:** {bet}")
            L.append("")
        if led and led.get("bet"):
            b = led["bet"]
            bits = []
            if "kicktipp_points" in b:
                bits.append(f"Kicktipp bet {b['kicktipp_bet']} → **{b['kicktipp_points']} pts**")
            if "kickgeist_correct" in b:
                bits.append(f"Kickgeist {b['kickgeist_pick']} "
                            f"({'✓' if b['kickgeist_correct'] else '✗'})")
            if bits:
                L.append("  • " + " · ".join(bits))
                L.append("")
        adj = p.get("adjusted") or {}
        if adj.get("reasoning"):
            L.append(f"_Rationale:_ {adj['reasoning']}")
            L.append("")

    # results / accuracy
    L.append("## Results / accuracy (cumulative, confirmed only)")
    L.append("")
    tot = ledger.get("totals", {})
    bt = tot.get("by_track", {})
    if bt:
        L.append("| Track | n | Tendency | Internal pts | Brier avg | LogLoss avg |")
        L.append("|---|---|---|---|---|---|")
        for t in ("model", "adjusted", "odds", "external"):
            v = bt.get(t, {})
            if v.get("n"):
                L.append(f"| {t} | {v['n']} | {v['tendency_correct']}/{v['n']} "
                         f"| {v['internal_pts']} | {v['brier_avg']} | {v['logloss_avg']} |")
        L.append("")
    kt = tot.get("kicktipp", {})
    kg = tot.get("kickgeist", {})
    if kt:
        L.append(f"- **Kicktipp:** {kt.get('points')}/{kt.get('max_possible')} pts "
                 f"over {kt.get('n')} scored bets.")
    if kg:
        L.append(f"- **Kickgeist:** {kg.get('correct')}/{kg.get('n')} correct "
                 f"({pct(kg.get('accuracy')) if kg.get('accuracy') is not None else '—'}).")
    L.append("")

    # elo movement for this day's matches
    day_ids = {p["match_id"] for p in day["predictions"]}
    moves = [u for u in hist.get("updates", []) if u["match_id"] in day_ids]
    if moves:
        L.append("## Elo movement")
        L.append("")
        for u in moves:
            L.append(f"- {u['match_id']} {name(u['home'])} {u['score']} {name(u['away'])}: "
                     f"{name(u['home'])} {u['r_home_before']}→{u['r_home_after']} "
                     f"({u['delta_home']:+.1f}), {name(u['away'])} "
                     f"{u['r_away_before']}→{u['r_away_after']}")
        L.append("")

    # simulation snapshot (latest available)
    sims = sorted(glob.glob(store.path("data/simulations/sim_*.json")))
    if sims:
        sim = store.load(os.path.relpath(sims[-1], store.ROOT))
        rows = sorted(sim["teams"].items(), key=lambda kv: -kv[1]["champion"])[:5]
        L.append(f"## Simulation (N={sim['n_iterations']}, "
                 f"{sim['n_confirmed_results']} results fixed)")
        L.append("")
        L.append("Top championship odds: "
                 + ", ".join(f"{name(t)} {d['champion']:.1%}" for t, d in rows) + ".")
        L.append("")

    L.append("## Status / gaps")
    L.append("")
    unlocked = [p["match_id"] for p in day["predictions"]
                if not p.get("locked_at") and p["match_id"] not in results]
    if unlocked:
        L.append(f"- Unlocked upcoming predictions: {', '.join(unlocked)}.")
    no_adj = [p["match_id"] for p in day["predictions"] if not p.get("adjusted")]
    if no_adj:
        L.append(f"- Missing adjusted (research) block: {', '.join(no_adj)}.")
    disputed = [mid for mid, r in results.items()
                if r["reconciliation"]["status"] == "disputed"]
    if disputed:
        L.append(f"- DISPUTED results to resolve: {', '.join(disputed)}.")
    L.append("")

    rel = f"reports/daily/{date}.md"
    store.save_text(rel, "\n".join(L))
    print(f"wrote {rel}")


if __name__ == "__main__":
    main()
