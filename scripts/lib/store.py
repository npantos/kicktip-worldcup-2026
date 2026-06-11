"""JSON persistence helpers. Stdlib only."""
import json
import os
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "data")
REPORTS = os.path.join(ROOT, "reports")


def path(*parts):
    return os.path.join(ROOT, *parts)


_MISSING = object()


def load(relpath, default=_MISSING):
    p = path(relpath)
    if not os.path.exists(p):
        if default is not _MISSING:
            return default
        raise FileNotFoundError(p)
    with open(p) as f:
        return json.load(f)


def save(relpath, obj):
    """Atomic write: temp file in the same dir, then rename."""
    p = path(relpath)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False, sort_keys=False)
            f.write("\n")
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def save_text(relpath, text):
    p = path(relpath)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(text)


def teams():
    return {t["id"]: t for t in load("data/teams.json")["teams"]}


def fixtures():
    return load("data/fixtures.json")["fixtures"]


def fixtures_by_id():
    return {m["match_id"]: m for m in fixtures()}


def results():
    return load("data/results/results.json", default={"results": []})["results"]


def confirmed_results():
    return [r for r in results() if r["reconciliation"]["status"] == "confirmed"]


def current_elo():
    hist = load("data/elo/ratings_history.json", default=None)
    if hist and hist.get("current"):
        return dict(hist["current"])
    init = load("data/elo/ratings_initial.json")
    return dict(init["ratings"])


if __name__ == "__main__":
    save("data/.selftest.json", {"ok": True, "n": [1, 2, 3]})
    assert load("data/.selftest.json") == {"ok": True, "n": [1, 2, 3]}
    os.unlink(path("data/.selftest.json"))
    print("store.py self-test OK")
