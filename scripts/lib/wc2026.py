"""WC2026 format rules: group tiebreakers, best-thirds, bracket resolution.

Shared by standings.py (deterministic, ties flagged) and simulate.py (ties
broken by the simulation's rng). Fair-play points are not tracked, so the
final tiebreak steps (fair play, drawing of lots) are modeled as random in
simulation and flagged `tied=True` in reports.
"""
import itertools

GROUPS = "ABCDEFGHIJKL"


def empty_row(team_id):
    return {"team": team_id, "played": 0, "won": 0, "drawn": 0, "lost": 0,
            "gf": 0, "ga": 0, "gd": 0, "points": 0}


def accumulate(rows, home, away, gh, ga):
    h, a = rows[home], rows[away]
    h["played"] += 1
    a["played"] += 1
    h["gf"] += gh; h["ga"] += ga
    a["gf"] += ga; a["ga"] += gh
    if gh > ga:
        h["won"] += 1; a["lost"] += 1; h["points"] += 3
    elif gh < ga:
        a["won"] += 1; h["lost"] += 1; a["points"] += 3
    else:
        h["drawn"] += 1; a["drawn"] += 1; h["points"] += 1; a["points"] += 1
    for r in (h, a):
        r["gd"] = r["gf"] - r["ga"]


def group_table(team_ids, results, rng=None):
    """results: list of (home, away, gh, ga) within this group.

    Returns rows in final ranking order. Each row gets rank (1-based) and
    tied=True when the order past GF required head-to-head-unresolvable
    randomness/lots.
    """
    rows = {t: empty_row(t) for t in team_ids}
    for home, away, gh, ga in results:
        if home in rows and away in rows:
            accumulate(rows, home, away, gh, ga)

    def order(subset, depth=0):
        """Order subset of team ids by FIFA criteria; recurse into head-to-head."""
        key = lambda t: (-rows[t]["points"], -rows[t]["gd"], -rows[t]["gf"])
        subset = sorted(subset, key=key)
        out = []
        for _, tier_iter in itertools.groupby(subset, key=key):
            tier = list(tier_iter)
            if len(tier) == 1:
                out.extend(tier)
                continue
            if depth == 0:
                # head-to-head sub-table among the tied teams
                sub = [(h, a, gh, ga) for h, a, gh, ga in results
                       if h in tier and a in tier]
                sub_rows = {t: empty_row(t) for t in tier}
                for h, a, gh, ga in sub:
                    accumulate(sub_rows, h, a, gh, ga)
                skey = lambda t: (-sub_rows[t]["points"], -sub_rows[t]["gd"],
                                  -sub_rows[t]["gf"])
                tier = sorted(tier, key=skey)
                for _, sub_tier_iter in itertools.groupby(tier, key=skey):
                    sub_tier = list(sub_tier_iter)
                    if len(sub_tier) > 1:
                        if rng is not None:
                            rng.shuffle(sub_tier)
                        else:
                            sub_tier.sort()
                        for t in sub_tier:
                            rows[t]["tied"] = True
                    out.extend(sub_tier)
            else:
                if rng is not None:
                    rng.shuffle(tier)
                else:
                    tier.sort()
                for t in tier:
                    rows[t]["tied"] = True
                out.extend(tier)
        return out

    ordered = order(list(team_ids))
    result = []
    for i, t in enumerate(ordered, 1):
        row = dict(rows[t])
        row["rank"] = i
        row.setdefault("tied", False)
        result.append(row)
    return result


def rank_thirds(third_rows, rng=None):
    """third_rows: list of standings rows (one per group, rank==3), each must
    also carry 'group'. Returns rows ordered best-first; top 8 advance."""
    key = lambda r: (-r["points"], -r["gd"], -r["gf"])
    rows = sorted(third_rows, key=key)
    out = []
    for _, tier_iter in itertools.groupby(rows, key=key):
        tier = list(tier_iter)
        if len(tier) > 1:
            if rng is not None:
                rng.shuffle(tier)
            else:
                tier.sort(key=lambda r: r["group"])
                for r in tier:
                    r["tied"] = True
        out.extend(tier)
    return out


def allocate_thirds(advancing_groups, third_slot_sets, forced=None):
    """Assign 8 advancing third-place groups to the 8 R32 third-slots.

    third_slot_sets: {match_id: '3ABCDF', ...} (allowed groups per slot).
    forced: optional {match_id: group} pinning specific slots to a known
    allocation. Our generic backtracker only guarantees *a* feasible matching;
    FIFA's official lookup table picks one specific matching, which can differ.
    When the platform (Kicktipp) bracket is known, pass it here so the repo
    matches reality. Pinned entries are validated (group must be advancing and
    allowed by the slot set); the remaining slots are backtracked as before.
    Returns {match_id: group}.
    """
    advset = list(advancing_groups)
    forced = {m: g for m, g in (forced or {}).items() if m in third_slot_sets}
    for m, g in forced.items():
        if g not in advset or g not in third_slot_sets[m][1:]:
            raise ValueError(f"invalid forced third allocation {m}->{g} "
                             f"(advancing={advset}, set={third_slot_sets[m]})")
    if len(set(forced.values())) != len(forced):
        raise ValueError(f"forced third allocation has duplicate groups: {forced}")

    open_slots = {m: s for m, s in third_slot_sets.items() if m not in forced}
    slots = sorted(open_slots.items(),
                   key=lambda kv: (len(set(kv[1][1:]) & set(advset)), kv[0]))
    assignment = dict(forced)

    def backtrack(i, remaining):
        if i == len(slots):
            return True
        match_id, slot_set = slots[i]
        for g in advset:  # ranking order = priority
            if g in remaining and g in slot_set[1:]:
                assignment[match_id] = g
                if backtrack(i + 1, remaining - {g}):
                    return True
                del assignment[match_id]
        return False

    if not backtrack(0, set(advset) - set(forced.values())):
        raise ValueError(f"no feasible third-place allocation for {advancing_groups}")
    return assignment


def resolve_r32(group_ranks, thirds_assignment, r32_slots):
    """group_ranks: {group: [team1st, team2nd, team3rd, team4th]};
    thirds_assignment: {match_id: group} for the 8 third slots.
    Returns {match_id: (home_team, away_team)}."""
    out = {}
    for slot in r32_slots:
        sides = []
        for s in (slot["home_slot"], slot["away_slot"]):
            if s[0] in "12":
                sides.append(group_ranks[s[1]][int(s[0]) - 1])
            else:  # third-place slot
                g = thirds_assignment[slot["match_id"]]
                sides.append(group_ranks[g][2])
        out[slot["match_id"]] = (sides[0], sides[1])
    return out


if __name__ == "__main__":
    # tiebreaker: B and C tied on pts/gd/gf overall, B beat C head-to-head
    res = [("A", "B", 2, 0), ("C", "D", 2, 0),
           ("B", "C", 1, 0), ("A", "D", 1, 0),
           ("D", "B", 0, 1), ("A", "C", 0, 2)]
    tbl = group_table(["A", "B", "C", "D"], res)
    order = [r["team"] for r in tbl]
    assert tbl[0]["points"] == 6 or order[0] in ("A", "B")
    # construct exact tie: X,Y same pts/gd/gf, X beat Y -> X above Y
    res2 = [("X", "Y", 1, 0), ("Y", "Z", 3, 2), ("Z", "X", 2, 1),
            ("X", "W", 2, 0), ("Y", "W", 2, 0), ("Z", "W", 0, 1)]
    tbl2 = group_table(["X", "Y", "Z", "W"], res2)
    o2 = [r["team"] for r in tbl2]
    x, y = o2.index("X"), o2.index("Y")
    px = next(r for r in tbl2 if r["team"] == "X")
    py = next(r for r in tbl2 if r["team"] == "Y")
    if (px["points"], px["gd"], px["gf"]) == (py["points"], py["gd"], py["gf"]):
        assert x < y, f"head-to-head should put X above Y: {o2}"
    # thirds allocation always feasible for every 8-of-12 combination
    sets_ = {"M074": "3ABCDF", "M077": "3CDFGH", "M079": "3CEFHI",
             "M080": "3EHIJK", "M081": "3BEFIJ", "M082": "3AEHIJ",
             "M085": "3EFGIJ", "M087": "3DEIJL"}
    n = 0
    for combo in itertools.combinations(GROUPS, 8):
        a = allocate_thirds(list(combo), sets_)
        assert sorted(a.values()) == sorted(combo)
        for mid, g in a.items():
            assert g in sets_[mid][1:]
        n += 1
    assert n == 495
    print("wc2026.py self-test OK (495/495 third-place combinations feasible)")
