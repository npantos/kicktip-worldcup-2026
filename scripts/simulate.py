#!/usr/bin/env python3
"""Monte Carlo tournament simulation -> championship odds.

Ratings are frozen at current Elo (no intra-simulation updates). Confirmed
results are fixed; everything else is sampled from the Elo->Poisson bridge.
Knockout draws go to extra time (lambda/3), then a 50/50 shootout.
"""
import argparse
import bisect
import os
import random
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import store, elo, poisson, wc2026

ROUND_ORDER = ["group", "r32", "r16", "qf", "sf", "final"]


class CdfCache:
    def __init__(self):
        self._c = {}

    def get(self, lam):
        key = round(lam, 3)
        if key not in self._c:
            acc, cdf = 0.0, []
            for k in range(poisson.MAX_GOALS + 1):
                acc += poisson.pmf(key, k)
                cdf.append(acc)
            self._c[key] = cdf
        return self._c[key]

    def sample(self, lam, rng):
        cdf = self.get(lam)
        return bisect.bisect_left(cdf, rng.random() * cdf[-1])


def sample_match(rh, ra, bonus, rng, cache, knockout=False):
    """-> (gh, ga, home_advances). 90' scoreline; knockout draws resolved."""
    lh, la = elo.lambdas(rh, ra, bonus)
    gh, ga = cache.sample(lh, rng), cache.sample(la, rng)
    if not knockout or gh != ga:
        return gh, ga, gh > ga
    eh, ea = cache.sample(lh / 3.0, rng), cache.sample(la / 3.0, rng)
    if eh != ea:
        return gh + eh, ga + ea, eh > ea
    return gh + eh, ga + ea, rng.random() < 0.5


def run(n_iter, seed):
    teams = store.teams()
    fixtures = store.fixtures()
    bt = store.load("data/bracket_template.json")
    ratings = store.current_elo()
    confirmed = {r["match_id"]: r for r in store.confirmed_results()}

    group_fx = [f for f in fixtures if f["stage"] == "group"]
    ko_fx = {f["match_id"]: f for f in fixtures if f["stage"] != "group"}
    rng = random.Random(seed)
    cache = CdfCache()

    tally = {t: {"win_group": 0, "r32": 0, "r16": 0, "qf": 0, "sf": 0,
                 "final": 0, "champion": 0} for t in teams}

    for _ in range(n_iter):
        # --- group stage
        results_by_group = {g: [] for g in wc2026.GROUPS}
        for f in group_fx:
            r = confirmed.get(f["match_id"])
            if r:
                gh, ga = r["home_goals"], r["away_goals"]
            else:
                bonus = elo.home_bonus(f["home"], f["away"], f["venue_country"])
                gh, ga, _adv = sample_match(ratings[f["home"]], ratings[f["away"]],
                                            bonus, rng, cache)
            results_by_group[f["group"]].append((f["home"], f["away"], gh, ga))

        group_ranks, thirds = {}, []
        for g in wc2026.GROUPS:
            ids = [t for t, tt in teams.items() if tt["group"] == g]
            rows = wc2026.group_table(ids, results_by_group[g], rng=rng)
            group_ranks[g] = [r["team"] for r in rows]
            third = dict(rows[2])
            third["group"] = g
            thirds.append(third)
            tally[rows[0]["team"]]["win_group"] += 1

        ranked = wc2026.rank_thirds(thirds, rng=rng)
        advancing = [r["group"] for r in ranked[:8]]
        assignment = wc2026.allocate_thirds(advancing, bt["third_slot_sets"])
        r32_pairs = wc2026.resolve_r32(group_ranks, assignment, bt["r32_slots"])

        # --- knockout
        slot_team = {}  # 'W089' -> team, etc.
        for mid, (h, a) in r32_pairs.items():
            slot_team[mid] = (h, a)
        for t_pair in r32_pairs.values():
            for t in t_pair:
                tally[t]["r32"] += 1

        winners, losers = {}, {}

        def play(mid, h, a, stage):
            r = confirmed.get(mid)
            f = ko_fx[mid]
            if r and f["home"] == h and f["away"] == a:
                gh, ga = r["home_goals"], r["away_goals"]
                if r.get("penalties"):
                    ph, pa = r["penalties"]
                    adv = (gh + ph) > (ga + pa)
                elif gh != ga:
                    adv = gh > ga
                else:
                    adv = rng.random() < 0.5
            else:
                bonus = elo.home_bonus(h, a, f["venue_country"])
                _gh, _ga, adv = sample_match(ratings[h], ratings[a], bonus, rng,
                                             cache, knockout=True)
            winners[mid] = h if adv else a
            losers[mid] = a if adv else h

        for mid in sorted(r32_pairs):
            h, a = r32_pairs[mid]
            play(mid, h, a, "r32")

        stage_of = {"r16": "r16", "qf": "qf", "sf": "sf", "final": "final"}
        for mid in sorted(bt["progression"]):
            f = ko_fx[mid]
            if f["stage"] == "third_place":
                continue
            ref = bt["progression"][mid]
            h = winners["M" + ref["home"][1:]] if ref["home"][0] == "W" else None
            a = winners["M" + ref["away"][1:]] if ref["away"][0] == "W" else None
            if h is None or a is None:
                continue
            tally[h][stage_of[f["stage"]]] += 1
            tally[a][stage_of[f["stage"]]] += 1
            play(mid, h, a, f["stage"])

        champ = winners["M104"]
        tally[champ]["champion"] += 1

    out = {
        "run_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n_iterations": n_iter, "seed": seed,
        "n_confirmed_results": len(confirmed),
        "teams": {t: {k: round(v / n_iter, 4) for k, v in d.items()}
                  for t, d in tally.items()},
    }
    return out


def render(sim, date):
    teams = store.teams()
    prev = None
    import glob
    sims = sorted(glob.glob(store.path("data/simulations/sim_*.json")))
    cur_path = store.path(f"data/simulations/sim_{date}.json")
    older = [s for s in sims if s < cur_path]
    if older:
        prev = store.load(os.path.relpath(older[-1], store.ROOT))

    rows = sorted(sim["teams"].items(), key=lambda kv: -kv[1]["champion"])
    lines = [f"# Championship odds", "",
             f"_Monte Carlo, N={sim['n_iterations']}, ratings as of {date}, "
             f"{sim['n_confirmed_results']} results fixed._", "",
             "| # | Team | Champion | Final | SF | QF | R16 | R32 | Win grp |"
             + (" Δ champ |" if prev else ""),
             "|---|------|----------|-------|----|----|-----|-----|---------|"
             + ("---------|" if prev else "")]
    for i, (t, d) in enumerate(rows, 1):
        line = (f"| {i} | {teams[t]['name']} | {d['champion']:.1%} | {d['final']:.1%} "
                f"| {d['sf']:.1%} | {d['qf']:.1%} | {d['r16']:.1%} | {d['r32']:.1%} "
                f"| {d['win_group']:.1%} |")
        if prev:
            delta = d["champion"] - prev["teams"].get(t, {}).get("champion", 0)
            line += f" {delta:+.1%} |"
        lines.append(line)
    lines.append("")
    store.save_text("reports/odds.md", "\n".join(lines))
    print("wrote reports/odds.md")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", "--iterations", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=20260611)
    ap.add_argument("--date", default=None, help="label date (default: today UTC)")
    args = ap.parse_args()
    date = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sim = run(args.iterations, args.seed)
    store.save(f"data/simulations/sim_{date}.json", sim)
    print(f"wrote data/simulations/sim_{date}.json")
    render(sim, date)


if __name__ == "__main__":
    main()
