# World Cup 2026 Prediction Center

A local prediction center for the FIFA World Cup 2026 (USA/Canada/Mexico, June 11 – July 19, 2026).
Claude acts as the prediction agent; plain-stdlib Python scripts compute everything deterministic.

## 🏆 [nemanj-ai.com](https://nemanj-ai.com/) — the season retrospective

The agent (**Nemanj-AI**) played the whole tournament in a 34-player Kicktipp league and **won it:
287 points, 1st of 34**, sealed with an exact 1:0 on the final. The full story — every bet, chart,
receipt and mistake — is told by the agent itself at **[nemanj-ai.com](https://nemanj-ai.com/)**
(*"The Machine Kept Receipts"*). The site is static, generated entirely from this repository's
data: source in [`site/`](site/), rebuilt with `python3 scripts/build_site.py`.

- **48 teams**, 12 groups of 4, **104 matches**; top 2 per group + 8 best third-placed teams → round of 32.
- Data lives in `data/` as JSON; human-readable outputs in `reports/` as markdown.
- The daily operating procedure is in [CLAUDE.md](CLAUDE.md).

## Prediction tracks (all scored against each other)

| Track | Produced by |
|---|---|
| `model` | Elo + Poisson baseline (`scripts/predict.py`) |
| `adjusted` | Claude's judgment on top of the model (injuries, form, news — with reasoning) |
| `odds` | Bookmaker-implied probabilities, overround removed (`scripts/lib/odds.py`) |
| `external` | Third-party predictions (API-Football `/predictions`, etc.) |

Accuracy: 3 pts exact score, 1 pt correct outcome, +1 knockout advance bonus; plus Ranked
Probability Score and Brier per track. See `reports/accuracy.md`.

## Scripts

Each runs standalone: `python3 scripts/<name>.py --help`

- `fetch_results.py` — pull results from APIs into `data/results/raw/` snapshots
- `reconcile_results.py` — raw snapshots → canonical `results.json` (confirmed/provisional/disputed)
- `update_elo.py` — apply confirmed results to Elo ratings (append-only history)
- `standings.py` — group tables, best-thirds race, qualification scenarios → `reports/standings.md`
- `predict.py` — model baselines for upcoming fixtures
- `score_accuracy.py` — score predictions vs confirmed results → ledger + `reports/accuracy.md`
- `simulate.py` — Monte Carlo tournament simulation → championship odds → `reports/odds.md`
- `daily_digest.py` — the daily report → `reports/daily/YYYY-MM-DD.md`
- `validate.py` — data sanity checks (run any time)

## External integrations (MCP)

> **Setup required by the user** — the agent sandbox cannot install MCP servers or third-party
> code itself. Run these once:

```bash
# 1. Kicktipp posting agent (https://github.com/christianheidorn/kicktipp-agent)
git clone https://github.com/christianheidorn/kicktipp-agent vendor/kicktipp-agent
cd vendor/kicktipp-agent && npm install && npx playwright install chromium && npm run build && npm link && cd ../..
export KICKTIPP_EMAIL=... KICKTIPP_PASSWORD=...      # never committed
claude mcp add kicktipp -- kicktipp-mcp

# 2. World Cup data tools (injuries, odds, news, standings — no key needed)
claude mcp add wc26 -- npx -y wc26-mcp

# 3. Kickgeist prediction pool (optional)
claude mcp add --transport http kickgeist https://mcp.kickgeist.com/mcp
```

Note (Alpine Linux): if `npx playwright install chromium` fails on musl, use the system browser
instead: `apk add chromium` and set `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1` plus
`PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium-browser` (or patch the launch options).

### REST data sources (optional keys, scripts skip silently if absent)

- `openfootball/worldcup.json` — schedule + results, no key
- API-Football (api-sports.io) — `API_FOOTBALL_KEY` env var, free tier 100 req/day; also its
  `/predictions` endpoint feeds the `external` track
- football-data.org — `FOOTBALL_DATA_TOKEN` env var

### Paid opt-ins (documented, not implemented)

- Apify `kindly_bolt/wc2026-actors-1` AI predictor ($50 / 1k predictions)
- Sportmonks World Cup API (enterprise)
- TheStatsAPI unified bookmaker odds ($50/mo)

### Credit

The odds-implied-probability track is inspired by
[antonengelhardt/Kicktipp-Bot](https://github.com/antonengelhardt/Kicktipp-Bot). We do not run
that bot — kicktipp-agent MCP is the single posting path (no double-submission). Its
scheduling/ntfy notification ideas are candidates for future enhancements.
