#!/usr/bin/env python3
"""Daily-cycle orchestrator for the World Cup 2026 prediction center.

Runs the deterministic backbone of the CLAUDE.md daily cycle in order, prints a
read-only pre-flight "to-do" dashboard, and HALTS at the steps that need the agent
(fetch results, ingest odds, research+adjust+lock, place Kicktipp bets) with exact
instructions. It is smart about already-bet / already-locked days, so a fully
pre-filled matchday runs the whole backbone hands-off.

It never reimplements the existing scripts — it shells out to them and reads JSON
state to drive the pre-flight and gating. Stdlib only.

Phases:
  status  read-only dashboard: what's played-but-unrecorded, disputed, today's
          lock/bet state, league-standings age, and the recommended next step.
          Makes NO changes.
  prep    reconcile -> [dispute hard-halt] -> score -> elo -> standings ->
          predict (baseline) -> validate.  Requires the agent to have fetched
          yesterday's results into raw snapshots first (step 1).
  bet     decision support for today: optimal_score + contest_strategy. Requires
          data/league/standings.json refreshed from the kicktipp MCP (step 9).
  close   simulate -> digest -> validate -> auto-commit (CLAUDE.md steps 10-12).
  all     (default) status -> prep, then close IFF the day is finalizable; else
          stop at the fetch/bet gate with instructions and re-run guidance.

Usage:
  python3 scripts/daily.py                       # --phase all, today (UTC-7)
  python3 scripts/daily.py --phase status
  python3 scripts/daily.py --phase prep
  python3 scripts/daily.py --phase bet
  python3 scripts/daily.py --phase close --no-commit
  python3 scripts/daily.py --date 2026-06-14
"""
import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS)
from lib import store                              # noqa: E402
from predict import match_day, is_locked, now_utc  # noqa: E402

ROOT = store.ROOT


# ----------------------------------------------------------------------------- helpers

def today_match_day():
    """The current match day (calendar date in UTC-7), matching predict.py."""
    return match_day(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))


def banner(text):
    print(f"\n==== {text} " + "=" * max(4, 64 - len(text)))


def fail(msg):
    print(f"\nABORT: {msg}", file=sys.stderr)
    return 1


def run_step(label, script, *extra):
    """Run a child script with the current interpreter; inherit stdout. Return rc."""
    print(f"\n--- [{label}] {script} {' '.join(extra)}".rstrip() + " ---")
    sys.stdout.flush()  # keep our headers ahead of the child's output when piped
    argv = [sys.executable, os.path.join(SCRIPTS, script), *extra]
    return subprocess.run(argv, cwd=ROOT).returncode


# ----------------------------------------------------------------------------- state reads

def kicktipp_bet(pred):
    """The active (non-superseded) Kicktipp bet on a prediction, or None."""
    for x in pred.get("posted_to", []):
        if x.get("platform") == "kicktipp" and not x.get("superseded_by"):
            return x.get("bet")
    return None


def disputed_results():
    return [r for r in store.results()
            if r.get("reconciliation", {}).get("status") == "disputed"]


def played_unconfirmed():
    """Fixtures that have kicked off but lack a confirmed result.

    Returns (fixture, reconciliation_status) where status is None (no snapshot),
    'provisional' (one source) or 'disputed'. These are the step-1 fetch to-do."""
    now = now_utc()
    confirmed = {r["match_id"] for r in store.confirmed_results()}
    rec_by_id = {r["match_id"]: r.get("reconciliation", {}) for r in store.results()}
    out = []
    for f in store.fixtures():
        if not f.get("home") or not f.get("away"):
            continue  # unresolved knockout slot
        if f["kickoff_utc"] < now and f["match_id"] not in confirmed:
            out.append((f, rec_by_id.get(f["match_id"], {}).get("status")))
    return out


def todays_fixtures(date):
    return sorted(
        (f for f in store.fixtures()
         if f.get("home") and match_day(f["kickoff_utc"]) == date),
        key=lambda f: f["kickoff_utc"])


def todays_predictions(date):
    day = store.load(f"data/predictions/{date}.json", default={"predictions": []})
    return {p["match_id"]: p for p in day["predictions"]}


def assess(date):
    """Decide whether the day can be finalized (closed) or is blocked by a gate.

    Returns (gate, message). gate is None when the deterministic backbone can be
    closed; otherwise one of 'dispute' / 'fetch' / 'bet' with a copy-pasteable
    instruction for the agent."""
    if disputed_results():
        return "dispute", ("Resolve disputed result(s) first (see the prep dispute gate), "
                           f"then re-run: python3 scripts/daily.py --date {date}")

    pu = played_unconfirmed()
    if pu:
        ids = " ".join(f["match_id"] for f, _ in pu)
        return "fetch", (
            f"FETCH results for: {ids}\n"
            "  Web-search the finals (FIFA/BBC/ESPN) or use the wc26 MCP, then write a\n"
            "  snapshot per source (>=2 independent sources to auto-confirm):\n"
            "    python3 scripts/fetch_results.py --manual '<json>'\n"
            f"  then re-run: python3 scripts/daily.py --date {date}")

    # Bet gate: today's still-upcoming matches that have no active Kicktipp bet.
    now = now_utc()
    preds = todays_predictions(date)
    missing = [f["match_id"] for f in todays_fixtures(date)
               if f["kickoff_utc"] > now
               and not kicktipp_bet(preds.get(f["match_id"], {}))]
    if missing:
        return "bet", (
            f"PLACE bets for: {' '.join(missing)}\n"
            f"  python3 scripts/daily.py --date {date} --phase bet   # decision support\n"
            "  then place via the kicktipp MCP (place_bets), read back with get_bets,\n"
            "  and record each in the prediction's posted_to[]. Finalize with:\n"
            f"    python3 scripts/daily.py --date {date} --phase close")

    return None, "Day is finalizable — running close (simulate, digest, commit)."


# ----------------------------------------------------------------------------- phases

def cmd_status(date):
    banner(f"Pre-flight  {date}")

    pu = played_unconfirmed()
    if pu:
        print("Played, not recorded (FETCH — step 1):")
        labels = {None: "no snapshot", "provisional": "1 source, needs a 2nd",
                  "disputed": "DISPUTED"}
        for f, st in pu:
            print(f"  {f['match_id']}  {f['home']}-{f['away']}  {f['kickoff_utc']}"
                  f"  [{labels.get(st, st)}]")
    else:
        print("Played, not recorded: none — results are up to date.")

    dsp = disputed_results()
    if dsp:
        print("\nDISPUTED results (resolve before scoring — step 2):")
        for r in dsp:
            print(f"  {r['match_id']}: {r['reconciliation'].get('disagreement')}")

    fxs = todays_fixtures(date)
    preds = todays_predictions(date)
    now = now_utc()
    print(f"\nToday's matches ({date}): {len(fxs)}")
    for f in fxs:
        p = preds.get(f["match_id"])
        if p is None:
            state = "no prediction yet (run prep)"
        else:
            bet = kicktipp_bet(p)
            state = ", ".join([
                "locked" if is_locked(p) else "unlocked",
                "adjusted" if p.get("adjusted") else "no adjusted block",
                f"bet {bet}" if bet else "NO BET",
                "kicked off" if f["kickoff_utc"] < now else "upcoming",
            ])
        print(f"  {f['match_id']}  {f['home']}-{f['away']}  {f['kickoff_utc']}  [{state}]")

    st = store.load("data/league/standings.json", default=None)
    if st:
        me = st.get("me", {})
        print(f"\nLeague (xcentric-ominimo): rank {me.get('rank')} / {st.get('field_size')}, "
              f"deficit {st.get('deficit_to_leader')} — fetched {st.get('fetched_at')} "
              f"(matchday {st.get('as_of_matchday')}). Refresh from the kicktipp MCP if stale.")
    else:
        print("\nLeague standings: data/league/standings.json missing — refresh from the kicktipp MCP.")

    gate, msg = assess(date)
    banner("Recommended next")
    print(msg)
    return 0


def cmd_prep(date):
    banner(f"PREP  {date}   reconcile -> score -> elo -> standings -> predict -> validate")

    rc = run_step("reconcile", "reconcile_results.py")
    if rc != 0:
        return fail(f"reconcile_results.py exited {rc}")

    dsp = disputed_results()
    if dsp:
        banner("DISPUTE GATE — hard halt")
        print("Disputed results must be resolved before scoring & Elo (CLAUDE.md step 2):")
        for r in dsp:
            print(f"  {r['match_id']}: {r['reconciliation'].get('disagreement')}")
        print("\nResolve each: investigate the disagreement, then either add a corrected\n"
              "raw snapshot (scripts/fetch_results.py --manual), or in\n"
              "data/results/results.json set that match's reconciliation.resolution_note\n"
              "and status='confirmed', manual=true. Then re-run prep.")
        return 1

    for label, script, *extra in [
        ("score", "score_accuracy.py"),
        ("elo", "update_elo.py"),
        ("standings", "standings.py"),
        ("predict", "predict.py", "--date", date),
        ("validate", "validate.py"),
    ]:
        rc = run_step(label, script, *extra)
        if rc != 0:
            return fail(f"{script} exited {rc}")

    banner("PREP done")
    gate, msg = assess(date)
    print(msg)
    if gate == "bet":
        print("\n(If you want to refine before betting: ingest odds [step 7] with\n"
              " predict.py --set-odds / --set-external, then research, fill each\n"
              " 'adjusted' block and set locked_at [step 8].)")
    return 0


def cmd_bet(date):
    banner(f"BET  {date}   optimal_score + contest_strategy (decision support)")

    preds = todays_predictions(date)
    if not preds:
        print("WARN: no predictions for today — run --phase prep first.")
    else:
        unlocked = sum(1 for p in preds.values() if not is_locked(p))
        no_adj = sum(1 for p in preds.values() if not p.get("adjusted"))
        if unlocked:
            print(f"NOTE: {unlocked}/{len(preds)} of today's predictions are unlocked — "
                  "set locked_at before the earliest kickoff once adjusted.")
        if no_adj:
            print(f"NOTE: {no_adj}/{len(preds)} have no 'adjusted' block — "
                  "strategy falls back to the odds/model track.")

    st = store.load("data/league/standings.json", default=None)
    if st is None:
        return fail("data/league/standings.json missing — contest_strategy needs it; "
                    "refresh from the kicktipp MCP first.")
    print(f"NOTE: league standings fetched {st.get('fetched_at')} "
          f"(matchday {st.get('as_of_matchday')}). Refresh from the kicktipp MCP if stale.")

    rc = run_step("optimal_score", "optimal_score.py", "--date", date)
    if rc != 0:
        return fail(f"optimal_score.py exited {rc}")
    rc = run_step("contest_strategy", "contest_strategy.py", "--date", date)
    if rc != 0:
        return fail(f"contest_strategy.py exited {rc}")

    banner("Place bets (agent)")
    print("Place the pick for the current contest mode above via the kicktipp MCP\n"
          "(place_bets), read back with get_bets, and record each in the prediction's\n"
          "posted_to[] (platform=kicktipp, bet, posted_at, confirmed_via). Then finalize:\n"
          f"  python3 scripts/daily.py --date {date} --phase close")
    return 0


def do_commit(date):
    st = subprocess.run(["git", "-C", ROOT, "status", "--porcelain"],
                        capture_output=True, text=True)
    if st.returncode != 0:
        return fail("git status failed")
    if not st.stdout.strip():
        print("\nNothing to commit — working tree clean.")
        return 0
    sys.stdout.flush()
    if subprocess.run(["git", "-C", ROOT, "add", "-A"]).returncode != 0:
        return fail("git add failed")
    msg = (f"Matchday {date}: daily cycle update\n\n"
           "Automated via scripts/daily.py (reconcile, score, Elo, standings,\n"
           "baseline predictions, simulate, digest).\n\n"
           "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>")
    if subprocess.run(["git", "-C", ROOT, "commit", "-m", msg]).returncode != 0:
        return fail("git commit failed")
    print(f"\nCommitted: Matchday {date}: daily cycle update")
    return 0


def cmd_close(date, commit, iterations):
    tail = " -> commit" if commit else ""
    banner(f"CLOSE  {date}   simulate -> digest -> validate{tail}")

    rc = run_step("simulate", "simulate.py", "-n", str(iterations), "--date", date)
    if rc != 0:
        return fail(f"simulate.py exited {rc}")
    rc = run_step("digest", "daily_digest.py", "--date", date)
    if rc != 0:
        return fail(f"daily_digest.py exited {rc}")
    rc = run_step("validate", "validate.py")
    if rc != 0:
        return fail(f"validate.py exited {rc} — NOT committing")

    if commit:
        return do_commit(date)
    print("\n--no-commit: skipping git commit. To commit manually:")
    print(f'  git -C {ROOT} add -A && git -C {ROOT} commit -m "Matchday {date}: daily cycle update"')
    return 0


def cmd_all(date, commit, iterations):
    cmd_status(date)
    rc = cmd_prep(date)
    if rc != 0:
        return rc  # dispute hard-halt (or a failed step)
    gate, msg = assess(date)
    if gate is not None:
        banner("GATE — agent action needed before finalizing")
        print(msg)
        return 0
    return cmd_close(date, commit, iterations)


# ----------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="WC2026 daily-cycle orchestrator")
    ap.add_argument("--phase", choices=["status", "prep", "bet", "close", "all"],
                    default="all", help="which segment to run (default: all)")
    ap.add_argument("--date", default=None,
                    help="match day YYYY-MM-DD (default: today in UTC-7)")
    ap.add_argument("--no-commit", action="store_true",
                    help="in close/all, skip the auto-commit (print the command instead)")
    ap.add_argument("-n", "--iterations", type=int, default=10000,
                    help="Monte-Carlo iterations for the simulate step (default 10000)")
    args = ap.parse_args()

    date = args.date or today_match_day()
    commit = not args.no_commit

    if args.phase == "status":
        rc = cmd_status(date)
    elif args.phase == "prep":
        cmd_status(date)
        rc = cmd_prep(date)
    elif args.phase == "bet":
        rc = cmd_bet(date)
    elif args.phase == "close":
        rc = cmd_close(date, commit, args.iterations)
    else:
        rc = cmd_all(date, commit, args.iterations)

    sys.exit(rc or 0)


if __name__ == "__main__":
    main()
