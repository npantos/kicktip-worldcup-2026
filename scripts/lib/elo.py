"""World Football Elo (eloratings.net convention) + Elo->Poisson goal-rate bridge.

K = 60 (World Cup finals). Home advantage +100 only when a host nation
(USA/CAN/MEX) plays in its own country. Penalty shootouts count as draws.
"""

K_WORLD_CUP = 60
HOME_ADV = 100
HOSTS = {"USA", "CAN", "MEX"}

# Goal-rate bridge: ~2.64 total goals at parity (recent World Cup average);
# at dr=+400 the split is roughly 2.4 : 0.7.
BASE_LAMBDA = 1.32
LAMBDA_DIVISOR = 600
LAMBDA_MIN, LAMBDA_MAX = 0.2, 4.0


def expected(dr):
    """Win expectancy for the side whose rating advantage is dr."""
    return 1.0 / (1.0 + 10.0 ** (-dr / 400.0))


def g_multiplier(margin):
    margin = abs(margin)
    if margin <= 1:
        return 1.0
    if margin == 2:
        return 1.5
    return (11.0 + margin) / 8.0


def home_bonus(home_id, away_id, city_country=None):
    """+100 if the home side is a host playing in its own country.

    city_country: 'USA'|'CAN'|'MEX' for the venue; if None, assume the listed
    home team gets the bonus only if it is a host nation (all WC2026 venues are
    in host countries, and FIFA schedules hosts' group games at home).
    """
    if home_id not in HOSTS:
        return 0
    if city_country is not None and city_country != home_id:
        return 0
    return HOME_ADV


def update(r_home, r_away, goals_home, goals_away, bonus=0, k=K_WORLD_CUP):
    """One match Elo update. Shootout results must be passed as the 120' draw.

    Returns (new_home, new_away, details).
    """
    dr = (r_home + bonus) - r_away
    we_home = expected(dr)
    if goals_home > goals_away:
        w_home = 1.0
    elif goals_home < goals_away:
        w_home = 0.0
    else:
        w_home = 0.5
    g = g_multiplier(goals_home - goals_away)
    delta = k * g * (w_home - we_home)
    details = {
        "k": k, "g": g, "dr": dr,
        "we_home": round(we_home, 4), "w_home": w_home,
        "delta_home": round(delta, 2),
    }
    return r_home + delta, r_away - delta, details


def lambdas(r_home, r_away, bonus=0):
    """Map rating difference to (lambda_home, lambda_away) Poisson goal rates."""
    dr = (r_home + bonus) - r_away
    lh = BASE_LAMBDA * 10.0 ** (dr / LAMBDA_DIVISOR)
    la = BASE_LAMBDA * 10.0 ** (-dr / LAMBDA_DIVISOR)
    clip = lambda x: max(LAMBDA_MIN, min(LAMBDA_MAX, x))
    return clip(lh), clip(la)


if __name__ == "__main__":
    assert abs(expected(0) - 0.5) < 1e-9
    assert abs(expected(200) + expected(-200) - 1.0) < 1e-9  # symmetry
    assert g_multiplier(0) == 1.0 and g_multiplier(1) == 1.0
    assert g_multiplier(2) == 1.5 and g_multiplier(3) == 1.75
    # equal teams, 1-0 home win, no bonus: home gains K * 0.5 = 30
    nh, na, d = update(1500, 1500, 1, 0)
    assert abs(nh - 1530) < 1e-9 and abs(na - 1470) < 1e-9
    # draw between equals: no change
    nh, na, _ = update(1600, 1600, 1, 1)
    assert nh == 1600 and na == 1600
    # rating sum conserved
    nh, na, _ = update(1700, 1450, 0, 3, bonus=100)
    assert abs((nh + na) - (1700 + 1450)) < 1e-9
    lh, la = lambdas(1500, 1500)
    assert abs(lh - BASE_LAMBDA) < 1e-9 and abs(la - BASE_LAMBDA) < 1e-9
    lh, la = lambdas(1900, 1500)
    assert lh > 2.0 and la < 0.8
    assert home_bonus("MEX", "RSA") == 100 and home_bonus("RSA", "MEX") == 0
    print("elo.py self-test OK")
