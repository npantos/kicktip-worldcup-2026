# Claude Design Brief — "The Nemanj-AI Campaign"

Copy everything below the line into Claude's design tool. Bring back whatever it
produces (palette hexes, type choices, component mockups, screenshots) and the site's
CSS will be restyled to match.

---

Design a visual identity and page design for a long-form, single-page, interactive
**sports-data-journalism website**, in the spirit of The Ringer's World Cup hub
(theringer.com/topic/world-cup) and their "NBA, Ranked" microsites
(nbarankings.theringer.com) — bold editorial sports storytelling fused with serious
data visualization.

**The story:** An AI prediction agent ("Nemanj-AI") entered a 34-player human office
betting league for the 2026 FIFA World Cup. It built its own data pipeline in Python,
priced all 104 matches four different ways (Elo model, de-vigged bookmaker odds, a
news-adjusted final call), placed bets through a browser it drove itself, ran 10,000
tournament simulations every day, and climbed from 11th place to 1st. The site is the
agent's own season retrospective, told in first person, in six numbered chapters:
01 The Setup · 02 The Machine · 03 The Season · 04 Defending First ·
05 The Knockout Diary · 06 Final Thoughts.

**Mood words:** stadium scoreboard, betting slip, terminal log, editorial longread,
"the machine kept receipts."

**Required components (design all of these):**
1. Hero: full-width editorial opening with a giant display headline and a 5-tile
   scoreboard stat strip (rank 1/34, 221+ points, 104 matches, 100+ bets, 360k sims).
2. Sticky section nav with 6 chapter links.
3. Chapter header pattern: big chapter number + uppercase title + one-line dek.
4. Line-chart panel style (used 4×: league points race, rank over time, calibration
   curves, championship-probability river) — captioned panels, annotation style for
   key events on a line, hover tooltip look.
5. Small "ticket"/stat cards (3-up row) and mono-spaced data-structure cards.
6. A horizontal pipeline diagram (9 nodes with arrows; 2 highlighted "judgment gates").
7. A knockout bracket (6 columns, 32 small match cards showing bet vs result vs points;
   winning tickets pop, losing tickets recede).
8. A dense sortable data table (6 columns, ~32 rows, monospace numerals).
9. Bonus-question cards (15 small cards with HIT / MISS / PENDING status chips).
10. A closing "final thoughts" featured card.

**Deliverables I need back:**
- A committed palette: 4–6 named hex values (ground, surface, text, muted, primary
  accent for the agent, secondary accent for "the field"/misses) — dark or light,
  your call, but it must feel like this subject and not a generic dashboard.
- Type system: display face + body face + data/mono face (Google Fonts only), with a
  type scale (hero, chapter title, dek, body, caption, data).
- Visual treatment rules for charts: line weights, grid style, how the agent's line
  is distinguished from the 33 humans, annotation/callout style.
- Mockups of: the hero, one chart panel, the bracket column, and the bonus-card grid —
  desktop (~1440px) and mobile (~390px).
- One aesthetic risk you'd take with this subject, and why it earns its place.

**Constraints:** single static HTML page, Chart.js for charts (styleable but canvas-
based), CSS only (no frameworks), must stay readable with long-form serif-friendly
body text (~68ch measure), WCAG AA contrast, and everything must degrade gracefully
on mobile with horizontally scrollable bracket/table.
