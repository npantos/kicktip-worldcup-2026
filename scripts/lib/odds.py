"""Bookmaker odds -> implied probabilities (overround removed).

Strategy borrowed from antonengelhardt/Kicktipp-Bot: the market is the
benchmark. We only de-vig by proportional normalization.
"""


def implied_probs(odds_home, odds_draw, odds_away):
    """Decimal odds -> (p_home, p_draw, p_away), normalized to sum 1."""
    for o in (odds_home, odds_draw, odds_away):
        if not o or o < 1.01:
            raise ValueError("decimal odds must be > 1.01, got %r" % (o,))
    raw = [1.0 / odds_home, 1.0 / odds_draw, 1.0 / odds_away]
    s = sum(raw)
    return tuple(p / s for p in raw)


def overround(odds_home, odds_draw, odds_away):
    """Bookmaker margin: sum of raw implied probs minus 1 (e.g. 0.05 = 5%)."""
    return 1.0 / odds_home + 1.0 / odds_draw + 1.0 / odds_away - 1.0


if __name__ == "__main__":
    p = implied_probs(2.0, 3.5, 4.0)
    assert abs(sum(p) - 1.0) < 1e-12
    assert p[0] > p[1] > p[2]
    # fair odds round-trip
    p = implied_probs(3.0, 3.0, 3.0)
    assert all(abs(x - 1 / 3) < 1e-12 for x in p)
    assert 0.0 < overround(1.9, 3.4, 4.2) < 0.15
    try:
        implied_probs(1.0, 3.0, 3.0)
        raise AssertionError("should have raised")
    except ValueError:
        pass
    print("odds.py self-test OK")
