#!/usr/bin/env python3
"""Group tables + best-thirds race -> reports/standings.md.

Also fills resolved knockout slots into fixtures.json once all results a slot
depends on are confirmed (group slots when the whole group is confirmed-final;
W###/L### slots when that match has a confirmed result).
"""
import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import store, wc2026


def confirmed_by_match():
    return {r["match_id"]: r for r in store.confirmed_results()}


def group_results(fixtures, results, group, include_provisional=False):
    out = []
    for f in fixtures:
        if f["stage"] != "group" or f["group"] != group:
            continue
        r = results.get(f["match_id"])
        if r:
            out.append((f["home"], f["away"], r["home_goals"], r["away_goals"]))
    return out


def compute_tables(include_provisional=False):
    """-> ({group: rows}, thirds_rows) using confirmed (+provisional) results."""
    teams = store.teams()
    fixtures = store.fixtures()
    results = {r["match_id"]: r for r in store.results()
               if r["reconciliation"]["status"] == "confirmed"
               or (include_provisional
                   and r["reconciliation"]["status"] == "provisional")}
    tables = {}
    thirds = []
    for g in wc2026.GROUPS:
        ids = [t["id"] for t in teams.values() if t["group"] == g]
        rows = wc2026.group_table(ids, group_results(fixtures, results, g))
        tables[g] = rows
        third = dict(rows[2])
        third["group"] = g
        thirds.append(third)
    return tables, wc2026.rank_thirds(thirds)


def fill_knockout_slots():
    """Resolve r32 group slots / W### / L### in fixtures.json from confirmed results."""
    data = store.load("data/fixtures.json")
    fixtures = data["fixtures"]
    by_id = {f["match_id"]: f for f in fixtures}
    results = confirmed_by_match()
    teams = store.teams()

    # group slots only when every match in the group is confirmed
    confirmed_group_count = {}
    for f in fixtures:
        if f["stage"] == "group" and f["match_id"] in results:
            confirmed_group_count[f["group"]] = confirmed_group_count.get(f["group"], 0) + 1
    complete = {g for g, n in confirmed_group_count.items() if n == 6}

    group_ranks = {}
    if complete:
        tables, thirds_ranked = compute_tables()
        for g in complete:
            group_ranks[g] = [r["team"] for r in tables[g]]

    thirds_assignment = {}
    if len(complete) == 12:
        _, thirds_ranked = compute_tables()
        advancing = [r["group"] for r in thirds_ranked[:8]]
        bt = store.load("data/bracket_template.json")
        thirds_assignment = wc2026.allocate_thirds(advancing, bt["third_slot_sets"])

    changed = 0

    def winner_loser(match_id):
        r = results.get(match_id)
        f = by_id.get(match_id)
        if not r or not f or f["home"] is None or f["away"] is None:
            return None, None
        gh, ga = r["home_goals"], r["away_goals"]
        if r.get("penalties"):
            ph, pa = r["penalties"]
            gh, ga = gh + ph, ga + pa  # decide by shootout
        if gh == ga:
            return None, None
        return ((f["home"], f["away"]) if gh > ga else (f["away"], f["home"]))

    for f in fixtures:
        if f["stage"] == "group" or f["home"] is not None:
            continue
        sides = {}
        for side in ("home", "away"):
            s = f[side + "_slot"]
            team = None
            if s[0] in "12" and s[1] in group_ranks:
                team = group_ranks[s[1]][int(s[0]) - 1]
            elif s[0] == "3" and f["match_id"] in thirds_assignment:
                team = group_ranks[thirds_assignment[f["match_id"]]][2]
            elif s[0] == "W":
                team = winner_loser("M" + s[1:])[0]
            elif s[0] == "L":
                team = winner_loser("M" + s[1:])[1]
            sides[side] = team
        if sides["home"] and sides["away"]:
            f["home"], f["away"] = sides["home"], sides["away"]
            changed += 1
            print(f"resolved {f['match_id']}: "
                  f"{teams[f['home']]['name']} vs {teams[f['away']]['name']}")
    if changed:
        store.save("data/fixtures.json", data)
    return changed


def render(include_provisional=False):
    teams = store.teams()
    tables, thirds = compute_tables(include_provisional)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"# Group standings", "",
             f"_Updated {now}. Based on confirmed results"
             + (" + provisional." if include_provisional else " only.") + "_", ""]
    for g in wc2026.GROUPS:
        lines.append(f"## Group {g}")
        lines.append("")
        lines.append("| # | Team | P | W | D | L | GF | GA | GD | Pts |")
        lines.append("|---|------|---|---|---|---|----|----|----|-----|")
        for r in tables[g]:
            flag = " †" if r.get("tied") else ""
            lines.append(
                f"| {r['rank']} | {teams[r['team']]['name']}{flag} | {r['played']} "
                f"| {r['won']} | {r['drawn']} | {r['lost']} | {r['gf']} | {r['ga']} "
                f"| {r['gd']:+d} | {r['points']} |")
        lines.append("")
    lines.append("## Best third-placed teams (top 8 advance)")
    lines.append("")
    lines.append("| # | Team | Grp | P | GD | GF | Pts |")
    lines.append("|---|------|-----|---|----|----|-----|")
    for i, r in enumerate(thirds, 1):
        cut = " ← cutoff" if i == 8 else ""
        flag = " †" if r.get("tied") else ""
        lines.append(f"| {i} | {teams[r['team']]['name']}{flag} | {r['group']} "
                     f"| {r['played']} | {r['gd']:+d} | {r['gf']} | {r['points']} |{cut}")
    lines.append("")
    lines.append("_† order among tied teams depends on fair play points / drawing"
                 " of lots (not tracked) — shown alphabetically._")
    lines.append("")
    store.save_text("reports/standings.md", "\n".join(lines))
    print("wrote reports/standings.md")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provisional", action="store_true",
                    help="include provisional results in the displayed tables")
    args = ap.parse_args()
    fill_knockout_slots()
    render(include_provisional=args.provisional)


if __name__ == "__main__":
    main()
