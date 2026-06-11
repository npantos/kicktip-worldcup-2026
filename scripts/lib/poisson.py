"""Scoreline distribution from two independent Poissons. Stdlib only."""
import math

MAX_GOALS = 10  # matrix truncation per side


def pmf(lam, k):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def score_matrix(lam_home, lam_away, max_goals=MAX_GOALS):
    """matrix[h][a] = P(home scores h, away scores a), renormalized over the truncation."""
    ph = [pmf(lam_home, k) for k in range(max_goals + 1)]
    pa = [pmf(lam_away, k) for k in range(max_goals + 1)]
    m = [[ph[h] * pa[a] for a in range(max_goals + 1)] for h in range(max_goals + 1)]
    total = sum(sum(row) for row in m)
    return [[v / total for v in row] for row in m]


def outcome_probs(matrix):
    """(p_home, p_draw, p_away) from a scoreline matrix."""
    ph = pd = pa = 0.0
    for h, row in enumerate(matrix):
        for a, v in enumerate(row):
            if h > a:
                ph += v
            elif h == a:
                pd += v
            else:
                pa += v
    return ph, pd, pa


def modal_score(matrix, tiebreak_home=True):
    """Most likely scoreline; ties go to the side indicated by tiebreak_home."""
    best, best_v = (0, 0), -1.0
    for h, row in enumerate(matrix):
        for a, v in enumerate(row):
            better = v > best_v + 1e-12
            tie = abs(v - best_v) <= 1e-12
            if better or (tie and tiebreak_home and h > a and best[0] <= best[1]):
                best, best_v = (h, a), max(v, best_v)
    return best


def sample_score(lam_home, lam_away, rng, max_goals=MAX_GOALS):
    """Sample one (h, a) scoreline. rng is a random.Random instance."""
    def sample_poisson(lam):
        # inverse-CDF sampling, truncated
        u = rng.random()
        acc = 0.0
        for k in range(max_goals + 1):
            acc += pmf(lam, k)
            if u <= acc:
                return k
        return max_goals
    return sample_poisson(lam_home), sample_poisson(lam_away)


if __name__ == "__main__":
    import random
    m = score_matrix(1.32, 1.32)
    assert abs(sum(sum(r) for r in m) - 1.0) < 1e-9
    ph, pd, pa = outcome_probs(m)
    assert abs(ph + pd + pa - 1.0) < 1e-9
    assert abs(ph - pa) < 1e-9  # symmetric at parity
    assert 0.20 < pd < 0.30  # natural draw rate for even WC match
    m2 = score_matrix(2.4, 0.7)
    ph2, pd2, pa2 = outcome_probs(m2)
    assert ph2 > 0.65 and pa2 < 0.12
    h, a = modal_score(m2)
    assert h >= 1 and h > a
    rng = random.Random(42)
    samples = [sample_score(2.4, 0.7, rng) for _ in range(4000)]
    mean_h = sum(s[0] for s in samples) / len(samples)
    mean_a = sum(s[1] for s in samples) / len(samples)
    assert abs(mean_h - 2.4) < 0.1 and abs(mean_a - 0.7) < 0.06
    print("poisson.py self-test OK")
