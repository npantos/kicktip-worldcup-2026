#!/usr/bin/env python3
"""Aggregate repo data into site/data.js for the tournament-retrospective website.

Reads every data store (plus the git history of data/league/standings.json for the
per-matchday league race) and emits a single JS payload consumed by site/index.html.
Regenerate any time with:  python3 scripts/build_site.py
Idempotent; safe to run after the final to refresh every chart and the pending-final
state in one shot.
"""
import json
import os
import re
import subprocess
import sys
from glob import glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import store

STAGE_LABEL = {
    "group": "Group", "r32": "Round of 32", "r16": "Round of 16",
    "qf": "Quarter-final", "sf": "Semi-final", "third_place": "Bronze final",
    "final": "Final",
}
KO_ORDER = ["r32", "r16", "qf", "sf", "third_place", "final"]
HEADLINE_TEAMS = ["ESP", "ARG", "FRA", "ENG", "BRA", "GER", "POR", "NED", "BEL", "MAR"]


def league_history():
    """Reconstruct the per-cycle league snapshots from git history (oldest first)."""
    rel = "data/league/standings.json"
    out = subprocess.run(
        ["git", "log", "--format=%H", "--", rel],
        cwd=store.ROOT, capture_output=True, text=True, check=True,
    ).stdout.split()
    snaps = []
    for h in reversed(out):
        try:
            blob = subprocess.run(
                ["git", "show", f"{h}:{rel}"],
                cwd=store.ROOT, capture_output=True, text=True, check=True,
            ).stdout
            snaps.append(json.loads(blob))
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            continue
    # working-tree copy may be newer than the last commit
    tree = store.load(rel, default=None)
    if tree and (not snaps or tree.get("fetched_at") != snaps[-1].get("fetched_at")):
        snaps.append(tree)
    # dedupe on fetched_at, keep order
    seen, uniq = set(), []
    for s in snaps:
        k = s.get("fetched_at")
        if k and k not in seen:
            seen.add(k)
            uniq.append(s)
    return uniq


def group_winners():
    """Parse rank-1 rows per group from reports/standings.md."""
    try:
        with open(store.path("reports", "standings.md"), encoding="utf-8") as f:
            md = f.read()
    except FileNotFoundError:
        return {}
    winners, grp = {}, None
    for line in md.splitlines():
        m = re.match(r"^## Group ([A-L])", line)
        if m:
            grp = m.group(1)
            continue
        if grp and re.match(r"^\|\s*1\s*\|", line):
            winners[grp] = line.split("|")[2].strip()
            grp = None
    return winners


def bonus_status(answers, winners, results_by_id, fixtures_by_id, boot=None):
    """Attach hit/miss/pending to each bonus answer."""
    sf_teams = set()
    for mid in ("M101", "M102"):
        fx = fixtures_by_id.get(mid, {})
        sf_teams.update(t for t in (fx.get("home"), fx.get("away")) if t)
    final = results_by_id.get("M104")
    fx_final = fixtures_by_id.get("M104", {})
    champion = None
    if final:
        champion = fx_final["home"] if final["home_goals"] > final["away_goals"] else fx_final["away"]
    teams = store.teams()
    name_of = {tid: t["name"] for tid, t in teams.items()}
    out = []
    for a in answers:
        q, ans = a["question"], a["answer"]
        status = "pending"
        m = re.match(r"Which team will win group ([A-L])", q)
        if m:
            status = "hit" if winners.get(m.group(1)) == ans else "miss"
        elif q.startswith("Who will reach the semi-finals"):
            picked = set(ans)
            actual = {name_of.get(t, t) for t in sf_teams}
            status = f"{len(picked & actual)}/4"
        elif "World Champion" in q:
            status = ("hit" if name_of.get(champion) == ans else "miss") if champion else "pending"
        elif "highest goal scorer" in q and boot:
            # resolved via the golden_boot record in data/bonus.json (official Golden Boot)
            status = "hit" if name_of.get(boot["team"], boot["team"]) == ans else "miss"
        out.append({**a, "status": status})
    return out


def bonus_players(winners, results_by_id, fixtures_by_id, boot=None):
    """Grade the top-5 players' public bonus picks (data/league/bonus_picks.json)."""
    picks = store.load("data/league/bonus_picks.json", default=None)
    if not picks:
        return []
    teams = store.teams()
    name_of = {tid: t["name"] for tid, t in teams.items()}
    fx_final = fixtures_by_id.get("M104", {})
    finalists = {fx_final.get("home"), fx_final.get("away")} - {None}
    res_final = results_by_id.get("M104")
    champion = None
    if res_final:
        champion = fx_final["home"] if res_final["home_goals"] > res_final["away_goals"] else fx_final["away"]
    sf_actual = set()
    for mid in ("M101", "M102"):
        fx = fixtures_by_id.get(mid, {})
        sf_actual.update(t for t in (fx.get("home"), fx.get("away")) if t)

    def champ_status(tid):
        if champion:
            return "hit" if tid == champion else "miss"
        return "pending" if tid in finalists else "miss"

    out = []
    for p in picks.get("players", []):
        items = [
            {"q": "World Champion", "answer": name_of.get(p["champion"], p["champion"]),
             "status": champ_status(p["champion"])},
            {"q": "Top-scorer team", "answer": name_of.get(p["top_scorer_team"], p["top_scorer_team"]),
             "status": ("hit" if p["top_scorer_team"] == boot["team"] else "miss") if boot else "pending"},
        ]
        for g in "ABCDEFGHIJKL":
            tid = p["groups"].get(g)
            nm = name_of.get(tid, tid)
            st = "pending"
            if winners.get(g):
                st = "hit" if winners[g] == nm else "miss"
            items.append({"q": f"Winner of group {g}", "answer": nm, "status": st})
        sf = p.get("semifinalists", [])
        hits = len(set(sf) & sf_actual)
        items.append({"q": "Semi-finalists", "answer": [name_of.get(t, t) for t in sf],
                      "status": f"{hits}/4"})
        out.append({"name": p["name"], "items": items})
    return out


def main():
    teams = store.teams()
    fixtures = store.fixtures()
    fixtures_by_id = {f["match_id"]: f for f in fixtures}
    results_by_id = {r["match_id"]: r for r in store.confirmed_results()}
    ledger = store.load("data/accuracy/ledger.json")
    ledger_by_id = {m["match_id"]: m for m in ledger.get("matches", [])}
    elo = store.load("data/elo/ratings_history.json")
    rules = store.load("data/kicktipp_rules.json")
    bonus = store.load("data/bonus.json")

    # ---- merged match list (chronological) -------------------------------
    matches = []
    for fx in sorted(fixtures, key=lambda f: (f["kickoff_utc"], f["match_id"])):
        mid = fx["match_id"]
        res = results_by_id.get(mid)
        led = ledger_by_id.get(mid, {})
        bet = (led.get("bet") or {})
        adj = (led.get("tracks") or {}).get("adjusted") or {}
        matches.append({
            "id": mid, "stage": fx["stage"], "stageLabel": STAGE_LABEL[fx["stage"]],
            "group": fx.get("group"), "date": fx["kickoff_utc"][:10],
            "kickoff": fx["kickoff_utc"], "city": fx.get("venue_city"),
            "home": fx.get("home"), "away": fx.get("away"),
            "homeName": teams.get(fx.get("home"), {}).get("name"),
            "awayName": teams.get(fx.get("away"), {}).get("name"),
            "score": f"{res['home_goals']}-{res['away_goals']}" if res else None,
            "note": (res.get("notes") or [None])[0] if res else None,
            "bet": bet.get("kicktipp_bet"), "pts": bet.get("kicktipp_points"),
            "adjProbs": adj.get("probs"), "adjScore": adj.get("predicted_score"),
            "status": fx.get("status"),
        })

    # ---- cumulative kicktipp points + track brier series -----------------
    cum, cum_series, briers = 0, [], {"model": [], "adjusted": [], "odds": []}
    sums = {"model": [0.0, 0], "adjusted": [0.0, 0], "odds": [0.0, 0]}
    for m in matches:
        led = ledger_by_id.get(m["id"])
        if not led:
            continue
        cum += (led.get("bet") or {}).get("kicktipp_points") or 0
        cum_series.append({"id": m["id"], "date": m["date"], "cum": cum,
                           "pts": (led.get("bet") or {}).get("kicktipp_points") or 0})
        for tr in briers:
            trk = (led.get("tracks") or {}).get(tr)
            if trk and trk.get("brier") is not None:
                sums[tr][0] += trk["brier"]
                sums[tr][1] += 1
                briers[tr].append(round(sums[tr][0] / sums[tr][1], 4))
            else:
                briers[tr].append(briers[tr][-1] if briers[tr] else None)

    # ---- Elo time series for headline teams ------------------------------
    elo_series = {t: [{"i": 0, "date": None, "r": teams[t]["elo_initial"]}] for t in HEADLINE_TEAMS}
    for i, u in enumerate(elo.get("updates", []), 1):
        for side, col in (("home", "r_home_after"), ("away", "r_away_after")):
            t = u[side]
            if t in elo_series:
                elo_series[t].append({"i": i, "date": u.get("applied_at", "")[:10], "r": round(u[col], 1)})

    # ---- champion probability over sim runs ------------------------------
    champ_series = []
    for f in sorted(glob(store.path("data", "simulations", "sim_*.json"))):
        sim = store.load(os.path.relpath(f, store.ROOT))
        row = {"date": os.path.basename(f)[4:14]}
        for t in HEADLINE_TEAMS:
            row[t] = round(sim["teams"].get(t, {}).get("champion", 0), 4)
        champ_series.append(row)

    # ---- league race from git history ------------------------------------
    race = []
    for s in league_history():
        me = s.get("me") or {}
        entry = {
            "fetched": s.get("fetched_at"), "date": (s.get("fetched_at") or "")[:10],
            "scored": s.get("matches_scored_so_far"),
            "rank": me.get("rank"), "points": me.get("points"), "bonus": me.get("bonus"),
            "top": [{"name": p.get("name"), "points": p.get("points"), "rank": p.get("rank")}
                    for p in (s.get("top") or [])],
        }
        race.append(entry)

    # ---- knockout diary ---------------------------------------------------
    preds = {}
    for f in sorted(glob(store.path("data", "predictions", "*.json"))):
        day = store.load(os.path.relpath(f, store.ROOT))
        for p in day.get("predictions", []):
            preds[p["match_id"]] = p
    ko = []
    for m in matches:
        if m["stage"] == "group":
            continue
        p = preds.get(m["id"], {})
        adj = p.get("adjusted") or {}
        bets = [{"bet": b.get("bet"), "at": b.get("posted_at"),
                 "superseded": bool(b.get("superseded_by")), "note": b.get("note")}
                for b in (p.get("posted_to") or []) if b.get("platform") == "kicktipp"]
        reasoning = adj.get("reasoning") or ""
        ko.append({**m,
                   "probs": [adj.get("p_home"), adj.get("p_draw"), adj.get("p_away")],
                   "predicted": adj.get("predicted_score"),
                   "reasoning": reasoning.split(". ")[0][:220],
                   "bets": bets})

    payload = {
        "generatedAt": ledger.get("updated_at"),
        "finalPending": fixtures_by_id.get("M104", {}).get("status") != "completed",
        "rules": rules.get("points"),
        "teams": {t: {"name": d["name"], "group": d["group"]} for t, d in teams.items()},
        "matches": matches,
        "cumPoints": cum_series,
        "briers": briers,
        "eloSeries": elo_series,
        "champSeries": champ_series,
        "race": race,
        "rankHistory": store.load("data/league/rank_history.json", default=None),
        "overview": store.load("data/league/overview_final.json", default=None),
        "bonus": bonus_status(bonus.get("answers", []), group_winners(), results_by_id, fixtures_by_id,
                              boot=bonus.get("golden_boot")),
        "bonusPlayers": bonus_players(group_winners(), results_by_id, fixtures_by_id,
                                      boot=bonus.get("golden_boot")),
        "bonusBasis": bonus.get("basis"),
        "ko": ko,
        "totals": ledger.get("totals"),
        "standingsNow": store.load("data/league/standings.json", default={}),
    }
    js = "window.SITE_DATA = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n"
    store.save_text("site/data.js", js)
    print(f"wrote site/data.js  ({len(js)//1024} KB; {len(matches)} matches, "
          f"{len(race)} league snapshots, {len(champ_series)} sim runs, finalPending={payload['finalPending']})")


if __name__ == "__main__":
    main()
