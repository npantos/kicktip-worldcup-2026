# World Cup 2026 Prediction Center — Agent Runbook

You are the prediction agent for this repo. Data is JSON under `data/`, reports are markdown
under `reports/`. All scripts are stdlib-only Python 3: `python3 scripts/<name>.py`.

## Hard rules

- **Never edit a locked prediction.** A prediction with `locked_at` in the past is immutable;
  scripts enforce this — do not bypass by editing JSON directly.
- **Never write credentials into the repo.** Kicktipp/API keys live in env vars only.
- Results are only *scored* and *applied to Elo* when `reconciliation.status == "confirmed"`
  (2+ independent sources agree). One source = `provisional`. Disagreement = `disputed` —
  investigate, write a `resolution_note`, set to `confirmed`.
- Raw snapshots in `data/results/raw/` are write-once; never edit, add a new snapshot instead.
- All timestamps in data files are UTC ISO-8601.

## Daily cycle (run each morning, again before first kickoff if news warrants)

1. **Fetch results** (yesterday + any finished today):
   - `python3 scripts/fetch_results.py --date YESTERDAY` (APIs → raw snapshots)
   - Web-search final scores (FIFA/BBC/ESPN) and/or use wc26-mcp tools; write a snapshot via
     `python3 scripts/fetch_results.py --manual '<json>'` with source attribution.
2. **Reconcile**: `python3 scripts/reconcile_results.py` — resolve any `disputed` before continuing.
3. **Score accuracy**: `python3 scripts/score_accuracy.py`
4. **Update Elo**: `python3 scripts/update_elo.py`
5. **Standings**: `python3 scripts/standings.py` (also fills resolved knockout slots into fixtures)
6. **Baseline predictions**: `python3 scripts/predict.py --date TODAY`
7. **Ingest odds + external predictions**: fetch bookmaker odds (wc26-mcp odds tool or web
   search), then `python3 scripts/predict.py --date TODAY --set-odds '<json>'`; same for
   API-Football predictions via `--set-external`.
8. **Adjust**: research each match (injuries, suspensions, lineups, form — wc26-mcp + web
   search). Edit today's `data/predictions/` file: fill each `adjusted` block (probs summing
   to 1, predicted score, reasoning, factors with source URLs). Stay within ±10pp of the model
   unless evidence is strong; if you stray far from the `odds` track, say why in `reasoning`.
   Set `locked_at` to now (must be before the earliest kickoff).
9. **Post picks**: run `python3 scripts/optimal_score.py --date TODAY` and bet the EP-max
   scoreline on the adjusted track (expected points under `data/kicktipp_rules.json` — this
   may differ from `predicted_score`). Kicktipp MCP `place_bets`; read back with `get_bets`
   to confirm. Then Kickgeist `predict_match` with the argmax outcome (H/D/A) of the adjusted
   track. Record both in the prediction's `posted_to` list, including the actual bet placed.
   Never post a match twice by accident; a deliberate pre-kickoff re-bet (e.g. after a
   platform scoring change) is allowed — mark the old entry `superseded_by` and add the new
   one with a `note`.
10. **Simulate**: `python3 scripts/simulate.py -n 10000`
11. **Digest**: `python3 scripts/daily_digest.py --date TODAY`
12. **Commit**: `git add -A && git commit -m "Matchday YYYY-MM-DD update"`

`python3 scripts/validate.py` any time something looks off.

## Data map

- `data/teams.json` — 48 teams, groups, FIFA rank, initial Elo (id = FIFA trigram)
- `data/fixtures.json` — 104 matches; knockout `home`/`away` are null until slots resolve
- `data/bracket_template.json` — R32 slot map + third-place allocation
- `data/results/results.json` — canonical reconciled results
- `data/elo/ratings_history.json` — append-only Elo updates + `current` map
- `data/predictions/YYYY-MM-DD.json` — per-day predictions, 4 tracks (model/adjusted/odds/external)
- `data/accuracy/ledger.json` — per-match scoring + running totals per track
- `data/simulations/sim_YYYY-MM-DD.json` — Monte Carlo outputs
  