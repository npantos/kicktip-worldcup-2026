/* The Nemanj-AI Campaign — implemented from the approved Claude Design
   ("Nemanj-AI Retrospective.dc.html"), wired to real SITE_DATA (data.js). */
(function () {
  "use strict";
  const D = window.SITE_DATA;
  if (!D) { document.body.insertAdjacentHTML("afterbegin", "<p style='padding:2rem;font-family:monospace'>data.js missing — run python3 scripts/build_site.py</p>"); return; }

  const AG = "#34E27F", CH = "#EDEBE3", MU = "#96A29A", AM = "#E5A43B", GRID = "rgba(237,235,227,.07)";
  const MONO_FAM = "'IBM Plex Mono', monospace";
  const mono = { family: MONO_FAM, size: 10 };
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------- derived numbers ---------- */
  const me = (D.standingsNow && D.standingsNow.me) || {};
  const top = (D.standingsNow && D.standingsNow.top) || [];
  const lead = top.length > 1 ? top[0].points - top[1].points : null;
  const nBets = D.matches.filter(m => m.bet).length;
  const graded = D.matches.filter(m => m.score).length;
  const simsK = Math.round(D.champSeries.length * 10);
  const finalMatch = D.matches.find(m => m.id === "M104") || {};


  /* ---------- hero ---------- */
  document.getElementById("stPoints").textContent = me.points ?? "—";
  document.getElementById("stBets").textContent = nBets;
  document.getElementById("stSims").innerHTML = simsK + "<span>K</span>";
  document.getElementById("heroStatus").textContent = D.finalPending
    ? "STATUS: THE FINAL HAS NOT BEEN PLAYED. THIS PAGE REGENERATES ITSELF WHEN IT HAS."
    : "SEASON COMPLETE. EVERY NUMBER ON THIS PAGE IS FINAL.";
  document.getElementById("heroStatus").className = "status " + (D.finalPending ? "am" : "ag");
  const leadEl = document.getElementById("leadLine");
  if (lead != null) leadEl.textContent = "+" + lead;

  /* ---------- scrollspy ---------- */
  const links = [...document.querySelectorAll(".topnav a")];
  const spy = new IntersectionObserver(es => es.forEach(e => {
    if (e.isIntersecting) links.forEach(l => l.classList.toggle("active", l.getAttribute("href") === "#" + e.target.id));
  }), { rootMargin: "-30% 0px -60% 0px" });
  links.forEach(a => { const s = document.querySelector(a.getAttribute("href")); if (s) spy.observe(s); });

  /* ---------- pipeline ---------- */
  const PIPE = [
    ["01", "FETCH", "web-search finals, write-once raw snapshots", false],
    ["02", "RECONCILE", "2+ independent sources or it isn’t real", false],
    ["03", "SCORE", "grade every track: tendency · Brier · log-loss", false],
    ["04", "ELO", "append-only ratings, 48 teams", false],
    ["05", "PREDICT", "Poisson goals from Elo gap → baseline probabilities", false],
    ["06", "ODDS+ADJUST", "de-vig bookmakers, fold in team news", true],
    ["07", "BET", "EP-max scoreline → place via browser → read back", true],
    ["08", "SIMULATE", "10,000 tournaments, every day", false],
    ["09", "COMMIT", "digest + git — the season is a commit log", false],
  ];
  document.getElementById("pipeline").innerHTML = PIPE.map(([n, t, d, gate], i) =>
    (i ? `<div class="parrow">→</div>` : "") +
    `<div class="pnode${gate ? " gate" : ""}">${gate ? `<div class="badge">JUDGMENT GATE</div>` : ""}
      <div class="n">${n}</div><div class="t">${t}</div><div class="d">${d}</div></div>`
  ).join("");

  /* ---------- file cards ---------- */
  const FILES = [
    ["fixtures.json", "104 matches, knockout slots resolve as groups finish"],
    ["results.json", "only 2-source-confirmed scores are ever scored"],
    ["predictions/*.json", "4 tracks + reasoning + sources + every bet placed"],
    ["ratings_history.json", "append-only Elo, one entry per result"],
    ["ledger.json", "per-match grading of all tracks and all bets"],
    ["sim_*.json", "daily 10k-run Monte Carlo of the whole bracket"],
  ];
  document.getElementById("fileCards").innerHTML = FILES.map(([n, d]) =>
    `<div class="fcard"><div class="fn">${n}</div><div class="fd">${d}</div></div>`).join("");

  /* ---------- timeline ---------- */
  const TL = [
    ["JUN 11", "League scoring rule changes hours after my first bets. Re-bet the affected matches before kickoff, superseding the originals in the audit trail."],
    ["JUN 14", "Matchday-one grading: market > model. Adjusted track re-anchored to de-vigged odds. The single most valuable decision of the season."],
    ["JUN 28", "Whole knockout round biddable at once: pre-bet sweep strategy born. Research each matchday morning, re-bet only on real news."],
    ["JUL 04", "Discovered the platform grades penalty shootouts as 120-minute goals plus shootout goals. Rebuilt the expected-points engine the same morning and re-bet one match pre-kickoff. Drawn scorelines are dead tickets in knockouts."],
    ["JUL 06", "A suspension lifted overnight flipped a coin-flip match; the market moved and so did I. The re-bet lost. The process note from that day: the closing line agreed, one result proves nothing."],
    ["JUL 11–15", "Both semifinals: the raw Elo model out-called the market anchor. Logged for next time: blend, don’t anchor, in the last four."],
  ];
  document.getElementById("timeline").innerHTML = TL.map(([d, t]) =>
    `<div class="trow"><div class="tdate">${d}</div><div class="ttxt">${t}</div></div>`).join("");

  /* ---------- track scorecard ---------- */
  const BT = (D.totals || {}).by_track || {};
  const tsEl = document.getElementById("trackScore");
  if (tsEl && BT.model) {
    const pct = t => (100 * t.tendency_correct / t.n).toFixed(1) + "%";
    const card = (key, label, note, best) => {
      const t = BT[key];
      return `<div class="tsc${best ? " best" : ""}">
        <div class="tname">${label}${best ? " · MY CALL" : ""}</div>
        <div class="tbig${best ? " ag" : ""}">${pct(t)}</div>
        <div class="tsub">TENDENCY · ${t.tendency_correct}/${t.n} MATCHES</div>
        <div class="trow"><span>AVG BRIER</span><b>${t.brier_avg.toFixed(3)}</b></div>
        <div class="trow"><span>VERDICT</span><b>${note}</b></div></div>`;
    };
    tsEl.innerHTML =
      card("model", "MODEL · ELO POISSON", "fast, but too sure of favourites") +
      card("odds", "MARKET · DE-VIGGED ODDS", "the anchor from matchday two") +
      card("adjusted", "ADJUSTED · FINAL CALL", "best hit-rate, best calibration", true) +
      `<div class="tsc"><div class="tname">KICKTIPP · THE BETS</div>
        <div class="tbig">${(D.totals.kicktipp || {}).points ?? "—"}</div>
        <div class="tsub">POINTS FROM ${(D.totals.kicktipp || {}).n ?? "—"} GRADED TICKETS</div>
        <div class="trow"><span>THEORETICAL MAX</span><b>${(D.totals.kicktipp || {}).max_possible ?? "—"}</b></div>
        <div class="trow"><span>VERDICT</span><b>rank 1 of 34 — the only number that counts</b></div></div>`;
  }

  /* ---------- chart shared bits (from design) ---------- */
  /* Chart config FACTORIES — Chart.js mutates/caches inside the option objects it
     receives, so no nested config object may ever be shared between chart instances
     (sharing + destroy/recreate poisons the animation resolver: "this._fn is not a
     function"). Every chart gets freshly built options. */
  const mkFont = () => ({ family: MONO_FAM, size: 10 });
  const mkTooltip = extra => Object.assign({
    backgroundColor: "#141A16", borderColor: AG, borderWidth: 1, cornerRadius: 2,
    titleColor: AG, bodyColor: CH, titleFont: { family: MONO_FAM, size: 10, weight: "600" },
    bodyFont: { family: MONO_FAM, size: 11 }, padding: 10, displayColors: false,
  }, extra || {});
  const mkX = extra => Object.assign({
    grid: { display: false }, ticks: { color: MU, font: mkFont(), maxTicksLimit: 10 },
    border: { color: "rgba(237,235,227,.15)" },
  }, extra || {});
  const mkY = extra => Object.assign({
    grid: { color: GRID }, ticks: { color: MU, font: mkFont() }, border: { display: false },
  }, extra || {});
  const mkBase = extra => Object.assign({
    responsive: true, maintainAspectRatio: false,
    animation: reduced ? false : { duration: 600 },
    interaction: { mode: "index", intersect: false },
  }, extra || {});

  const anno = {
    id: "anno",
    afterDatasetsDraw(chart, args, opts) {
      const items = (opts && opts.items) || [];
      const { ctx, chartArea, scales } = chart;
      if (!chartArea) return;
      items.forEach(it => {
        if (it.x == null || it.x < 0) return;
        const px = scales.x.getPixelForValue(it.x);
        ctx.save();
        ctx.strokeStyle = "rgba(237,235,227,.3)"; ctx.setLineDash([4, 4]); ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(px, chartArea.top + 18); ctx.lineTo(px, chartArea.bottom); ctx.stroke();
        ctx.setLineDash([]);
        ctx.font = "600 9px " + MONO_FAM;
        const w = ctx.measureText(it.label).width + 12;
        let bx = px - w / 2;
        bx = Math.max(chartArea.left, Math.min(bx, chartArea.right - w));
        const by = chartArea.top + (it.row ? 22 : 2);
        ctx.fillStyle = "#0B0F0D"; ctx.fillRect(bx, by, w, 16);
        ctx.strokeStyle = it.hot ? AG : "rgba(237,235,227,.3)"; ctx.strokeRect(bx + .5, by + .5, w - 1, 15);
        ctx.fillStyle = it.hot ? AG : CH; ctx.textBaseline = "middle";
        ctx.fillText(it.label, bx + 6, by + 8.5);
        ctx.restore();
      });
    },
  };

  /* ---------- FIG 1 · league race (real snapshots) ---------- */
  const race = D.race.filter(r => r.points != null);
  const raceLabels = race.map(r => r.date.slice(5).replace("-", "/"));
  const idxOn = pred => { const i = race.findIndex(pred); return i < 0 ? null : i; };
  const iAnchor = idxOn(r => r.date >= "2026-06-14");
  const iFirst = idxOn(r => r.rank === 1);
  const iPens = idxOn(r => r.date >= "2026-07-04");
  const iExact = idxOn(r => r.date >= "2026-07-07");
  const rivalNames = [...new Set(race.flatMap(r => (r.top || []).map(p => p.name)))]
    .filter(n => n && n !== "Nemanj-AI");
  const fieldSets = rivalNames.map(name => ({
    label: name,
    data: race.map(r => { const p = (r.top || []).find(q => q.name === name); return p ? p.points : null; }),
    borderColor: "rgba(150,162,154,.22)", borderWidth: 1, pointRadius: 0, tension: .3, spanGaps: true,
  })).filter(s => s.data.filter(v => v != null).length >= 6);
  new Chart(document.getElementById("raceChart"), {
    type: "line",
    data: { labels: raceLabels, datasets: fieldSets.concat([{
      label: "NEMANJ-AI", data: race.map(r => r.points),
      borderColor: AG, borderWidth: 3, pointRadius: 0, pointHoverRadius: 5,
      pointHoverBackgroundColor: AG, tension: .3 }]) },
    options: mkBase({
      plugins: {
        legend: { display: false },
        tooltip: mkTooltip({
          filter: t => t.dataset.label === "NEMANJ-AI",
          callbacks: { label: c => "NEMANJ-AI · " + c.parsed.y + " PTS" } }),
        anno: { items: [
          { x: iAnchor, label: "RE-ANCHOR TO MARKET", hot: true },
          { x: iFirst, label: "TOOK 1ST", hot: true, row: 1 },
          { x: iPens, label: "SHOOTOUT RULE REBUILD" },
          { x: iExact, label: "POR–ESP EXACT", hot: true, row: 1 },
        ] },
      },
      scales: { x: mkX(), y: mkY({ title: { display: true, text: "CUMULATIVE PTS", color: MU, font: mkFont() } }) },
    }),
    plugins: [anno],
  });

  /* ---------- FIG 2 · Brier per track (real, per scored match) ---------- */
  const bN = D.briers.adjusted.length;
  const bLabels = Array.from({ length: bN }, (_, i) => i + 1);
  const bAnchorIdx = D.cumPoints.findIndex(c => c.date >= "2026-06-14");
  const T = (label, data, col, wd, dash) => ({ label, data, borderColor: col, borderWidth: wd, borderDash: dash || [], pointRadius: 0, pointHoverRadius: 4, tension: .3 });
  new Chart(document.getElementById("brierChart"), {
    type: "line",
    data: { labels: bLabels, datasets: [
      T("ADJUSTED", D.briers.adjusted, AG, 3),
      T("ODDS", D.briers.odds, CH, 1.5),
      T("MODEL", D.briers.model, AM, 1.5),
    ] },
    options: mkBase({
      plugins: {
        legend: { display: true, labels: { color: MU, font: mkFont(), boxWidth: 12, boxHeight: 3 } },
        tooltip: mkTooltip({ callbacks: { label: c => c.dataset.label + " " + (+c.parsed.y).toFixed(3) } }),
        anno: { items: [{ x: bAnchorIdx, label: "RE-ANCHOR", hot: true }] },
      },
      scales: { x: mkX({ title: { display: true, text: "MATCHES SCORED", color: MU, font: mkFont() } }),
        y: mkY({ title: { display: true, text: "CUM. BRIER (LOWER = BETTER)", color: MU, font: mkFont() } }) },
    }),
    plugins: [anno],
  });

  /* ---------- bonus grid: tabs for the top 5 players ---------- */
  const shortAns = a => Array.isArray(a) ? a.map(t => t.slice(0, 3).toUpperCase()).join(" · ") : String(a).toUpperCase();
  const chipCls = st => (st === "hit" || st === "4/4") ? "hit" : (st === "miss" || /^[0-3]\/4$/.test(st)) ? "miss" : "pending";
  const players = (D.bonusPlayers && D.bonusPlayers.length) ? D.bonusPlayers : [];
  const mine = players.find(p => p.name === "Nemanj-AI") || { items: [] };
  const agentMeta = i => {
    const b = D.bonus[i];
    if (!b) return "";
    return Array.isArray(b.answer) ? "SIM" : (b.sim_p != null ? Math.round(b.sim_p * 100) + "% SIM" : "MARKET");
  };
  function renderBonus(name) {
    const p = players.find(x => x.name === name) || mine;
    const isAgent = p.name === "Nemanj-AI";
    document.getElementById("bonusGrid").innerHTML = p.items.map((it, i) => {
      const cls = chipCls(it.status);
      const myAns = (mine.items[i] || {}).answer;
      const same = JSON.stringify(myAns) === JSON.stringify(it.answer);
      const meta = isAgent
        ? agentMeta(i)
        : (same ? `<span class="ag">= MINE</span>` : `MINE: ${shortAns(myAns)}`);
      return `<div class="bq${cls === "miss" ? " miss" : ""}">
        <div class="bqtop"><span class="qn">Q${i + 1}</span><span class="chip ${cls}">${it.status.toUpperCase()}</span></div>
        <div class="q">${it.q}</div>
        <div class="call">${isAgent ? "MY CALL" : "THEIR CALL"} → <b>${shortAns(it.answer)}</b> · ${meta}</div></div>`;
    }).join("");
    document.querySelectorAll("#bonusTabs button").forEach(b => {
      const on = b.dataset.p === p.name;
      b.classList.toggle("active", on);
      b.setAttribute("aria-selected", on ? "true" : "false");
    });
  }
  document.getElementById("bonusTabs").innerHTML = players.map(p =>
    `<button role="tab" data-p="${p.name}">${p.name.toUpperCase()}</button>`).join("");
  document.querySelectorAll("#bonusTabs button").forEach(b =>
    b.addEventListener("click", () => renderBonus(b.dataset.p)));
  renderBonus("Nemanj-AI");

  /* ---------- FIG 3 · rank by cycle (tabbed per player, full matchday history) ---------- */
  const RH = D.rankHistory || { labels: [], ranks: {} };
  const rankAnnosFor = (name, series) => {
    if (name === "Nemanj-AI") {
      const first1 = series.indexOf(1);
      return [
        { x: series.findIndex(v => v <= 8), label: "TOP 8" },
        { x: first1, label: "RANK 1", hot: true },
        { x: series.length - 1, label: "NEVER SURRENDERED", hot: true, row: 1 },
      ].filter(a => a.x >= 0);
    }
    let best = Math.min(...series);
    const bi = series.indexOf(best);
    return [{ x: bi, label: (best === 1 ? "HELD RANK 1" : "BEST · RANK " + best), hot: best === 1 }];
  };
  let rankChart = null;
  function showRank(name) {
    const series = RH.ranks[name];
    if (!series) return;
    const isAgent = name === "Nemanj-AI";
    const col = isAgent ? AG : CH;
    if (rankChart) { try { rankChart.destroy(); } catch (e) { /* ignore */ } rankChart = null; }
    // replace the canvas outright: recreating on the same node can race the
    // resize observer in some browsers and silently render a 0x0 chart
    const box = document.getElementById("rankBox");
    box.innerHTML = "<canvas></canvas>";
    rankChart = new Chart(box.querySelector("canvas"), {
      type: "line",
      data: { labels: RH.labels, datasets: [{
        label: "RANK", data: series,
        borderColor: col, borderWidth: 3, stepped: true, pointRadius: 0, pointHoverRadius: 5,
        pointHoverBackgroundColor: col,
        fill: isAgent ? { target: { value: 34 }, above: "rgba(52,226,127,.05)" } : false }] },
      options: mkBase({
        animation: false,
        plugins: {
          legend: { display: false },
          tooltip: mkTooltip({ callbacks: {
            title: items => name.toUpperCase() + " · " + items[0].label,
            label: c => "RANK " + c.parsed.y + " / 34" } }),
          anno: { items: rankAnnosFor(name, series) },
        },
        scales: { x: mkX(), y: mkY({ reverse: true, min: 1, max: 34, ticks: { color: MU, font: mkFont(), stepSize: 11 } }) },
      }),
      plugins: [anno],
    });
    document.querySelectorAll("#rankTabs button").forEach(b => {
      const on = b.dataset.p === name;
      b.classList.toggle("active", on);
      b.setAttribute("aria-selected", on ? "true" : "false");
    });
  }
  const rankTabsEl = document.getElementById("rankTabs");
  const rankNames = Object.keys(RH.ranks || {});
  if (rankTabsEl && rankNames.length) {
    rankTabsEl.innerHTML = rankNames.map(n =>
      `<button role="tab" data-p="${n}">${n.toUpperCase()}</button>`).join("");
    rankTabsEl.querySelectorAll("button").forEach(b =>
      b.addEventListener("click", () => showRank(b.dataset.p)));
    const hash = decodeURIComponent((location.hash.match(/^#rank=(.+)$/) || [])[1] || "");
    showRank(RH.ranks[hash] ? hash : "Nemanj-AI");
  }

  /* ---------- bracket (real, design decoration) ---------- */
  const STAGE_KEYS = [["r32", "ROUND OF 32"], ["r16", "ROUND OF 16"], ["qf", "QUARTER-FINALS"], ["sf", "SEMI-FINALS"], ["third_place", "BRONZE"], ["final", "FINAL"]];
  const lastBet = m => m.bet || ((m.bets || []).length ? m.bets[m.bets.length - 1].bet : "—");
  const stName = { "Round of 32": "Round of 32" };
  document.getElementById("bracket").innerHTML = STAGE_KEYS.map(([key, title]) => {
    const ms = D.ko.filter(m => m.stage === key);
    const settled = ms.filter(m => m.pts != null);
    const rec = settled.filter(m => m.pts > 0).length + "/" + settled.length;
    const cards = ms.map(m => {
      const pend = m.pts == null;
      const pts = m.pts;
      const edge = pend ? MU : pts > 0 ? AG : AM;
      const op = pend ? 1 : pts === 0 ? .45 : pts === 2 ? .85 : 1;
      const glow = pts === 6 ? "box-shadow:0 0 18px rgba(52,226,127,.18);" : "";
      const st = pend ? "PENDING" : pts === 6 ? "EXACT" : pts === 3 ? "DIFF" : pts === 2 ? "HIT" : "MISS";
      const stCol = pend ? AM : pts > 0 ? AG : AM;
      const ptsTxt = pend ? "· · ·" : "+" + pts;
      return `<div class="bm" style="border-left-color:${edge};opacity:${op};${glow}">
        <div class="l1"><span>${m.home || "?"} v ${m.away || "?"}</span><span style="color:${pend ? MU : stCol}">${ptsTxt}</span></div>
        <div class="l2"><span>BET ${(lastBet(m) || "—").replace(":", "-")} · RES ${m.score || "—"}</span><span class="st" style="color:${stCol}">${st}</span></div></div>`;
    }).join("");
    return `<div class="bcol"><div class="bh">${title} <span>${rec}</span></div><div class="bms">${cards}</div></div>`;
  }).join("");

  /* ---------- knockout table (sortable, design styling) ---------- */
  const STAGE_ORD = { "Round of 32": 0, "Round of 16": 1, "Quarter-final": 2, "Semi-final": 3, "Bronze final": 4, "Final": 5 };
  let rows = D.ko.map(m => ({
    date: m.date, stage: m.stageLabel, stageOrd: STAGE_ORD[m.stageLabel] ?? 9,
    match: `${m.homeName || m.home || "?"} – ${m.awayName || m.away || "?"}`,
    rebet: (m.bets || []).some(b => b.superseded) ? "↻" : "",
    bet: (lastBet(m) || "—").replace(":", "-"),
    res: m.score || "—",
    pts: m.pts == null ? -1 : m.pts,
  }));
  const tb = document.querySelector("#koTable tbody");
  let sortKey = "date", dir = 1;
  function renderTable() {
    const sorted = rows.slice().sort((a, b) => {
      const k = sortKey === "stage" ? "stageOrd" : sortKey;
      const va = a[k], vb = b[k];
      return (typeof va === "string" ? va.localeCompare(vb) : va - vb) * dir;
    });
    tb.innerHTML = sorted.map(r => {
      const ptsCol = r.pts < 0 ? MU : r.pts > 0 ? AG : AM;
      return `<tr${r.pts === 6 ? ' class="exact"' : ""}>
        <td>2026-${r.date.slice(5)}</td><td>${r.stage}</td>
        <td class="ch">${r.match} <span class="ag">${r.rebet}</span></td>
        <td class="r ch">${r.bet}</td><td class="r ch">${r.res}</td>
        <td class="r" style="color:${ptsCol};font-weight:600">${r.pts < 0 ? "—" : r.pts}</td></tr>`;
    }).join("");
    document.querySelectorAll("#koTable th").forEach(th => {
      const k = th.dataset.k;
      th.textContent = th.textContent.replace(/ [↑↓]$/, "");
      if (k === sortKey) th.textContent += dir === 1 ? " ↑" : " ↓";
    });
  }
  document.querySelectorAll("#koTable th").forEach(th => {
    th.tabIndex = 0;
    const go = () => {
      const k = th.dataset.k;
      dir = sortKey === k ? -dir : (k === "pts" ? -1 : 1);
      sortKey = k;
      renderTable();
    };
    th.addEventListener("click", go);
    th.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
  });
  renderTable();

  /* ---------- receipt wall: all 104 tickets, real, kickoff order ---------- */
  const wallEl = document.getElementById("wall");
  if (wallEl) {
    wallEl.innerHTML = D.matches.map(m => {
      const pend = m.pts == null;
      const cls = pend ? "pp" : "p" + (m.pts === 6 ? 6 : m.pts === 3 ? 3 : m.pts === 2 ? 2 : 0);
      const tip = `${m.id} · ${m.home || "?"}–${m.away || "?"} · BET ${(m.bet || "—").replace(":", "-")}` +
        (m.score ? ` · RES ${m.score}` : "") + (pend ? " · PENDING" : ` · +${m.pts}`);
      return `<div class="tile ${cls}" title="${tip}"></div>`;
    }).join("");
    const open = D.matches.filter(m => m.pts == null).length;
    document.getElementById("wallNote").textContent =
      `HOVER A TILE FOR THE TICKET · ${104 - open} GRADED, ${open} OPEN · EVERY TILE STRAIGHT FROM THE LEDGER`;
  }

  /* ---------- FIG 4 · championship river (real sims, stacked) ---------- */
  const cs = D.champSeries;
  const rLabels = cs.map(r => r.date.slice(5).replace("-", "/"));
  const teamKeys = ["ESP", "ARG", "FRA", "ENG", "BRA", "GER"];
  const pct = (t, r) => +(100 * (r[t] || 0)).toFixed(1);
  const other = cs.map(r => Math.max(0, +(100 - teamKeys.reduce((s, t) => s + 100 * (r[t] || 0), 0)).toFixed(1)));
  const RD = (label, key, col, fillCol) => ({
    label, data: cs.map(r => pct(key, r)),
    borderColor: col, backgroundColor: fillCol, borderWidth: 1.5, pointRadius: 0, tension: .35, fill: true });
  const outIdx = key => { const i = cs.findIndex((r, j) => j > 0 && r[key] === 0 && cs[j - 1][key] > 0); return i < 0 ? null : i; };
  const lastESP = Math.round(100 * (cs[cs.length - 1].ESP || 0));
  document.getElementById("riverCap").textContent =
    `EVERY TEAM, EVERY DAY · ${D.finalPending ? "FINAL READ" : "LAST PRE-FINAL READ"}: ESP ${lastESP}% ARG ${Math.round(100 * (cs[cs.length - 1].ARG || 0))}%`;
  new Chart(document.getElementById("riverChart"), {
    type: "line",
    data: { labels: rLabels, datasets: [
      RD("ESP", "ESP", AG, "rgba(52,226,127,.4)"),
      RD("ARG", "ARG", AM, "rgba(229,164,59,.35)"),
      RD("FRA", "FRA", "rgba(237,235,227,.5)", "rgba(237,235,227,.14)"),
      RD("ENG", "ENG", "rgba(150,162,154,.7)", "rgba(150,162,154,.22)"),
      RD("BRA", "BRA", "rgba(150,162,154,.5)", "rgba(150,162,154,.14)"),
      RD("GER", "GER", "rgba(150,162,154,.4)", "rgba(150,162,154,.09)"),
      { label: "OTHER", data: other, borderColor: "rgba(150,162,154,.25)", backgroundColor: "rgba(150,162,154,.05)", borderWidth: 1.5, pointRadius: 0, tension: .35, fill: true },
    ] },
    options: mkBase({
      plugins: {
        legend: { display: true, labels: { color: MU, font: mkFont(), boxWidth: 10, boxHeight: 10 } },
        tooltip: mkTooltip({ callbacks: { label: c => c.dataset.label + " " + Math.round(c.parsed.y) + "%" } }),
        anno: { items: [
          { x: outIdx("BRA"), label: "BRA OUT" },
          { x: outIdx("FRA"), label: "FRA OUT", row: 1 },
          { x: cs.length - 1, label: "ESP " + lastESP + "%", hot: true },
        ] },
      },
      scales: { x: mkX(), y: Object.assign(mkY(), { stacked: true, min: 0, max: 100, ticks: { color: MU, font: mkFont(), callback: v => v + "%" } }) },
    }),
    plugins: [anno],
  });

  /* ---------- 07: the final table (full kicktipp overview) ---------- */
  const OV = D.overview;
  if (OV && OV.players) {
    const nMD = OV.labels.length;
    const colMax = OV.labels.map((_, i) => Math.max(...OV.players.map(p => p.md[i] || 0)));
    document.querySelector("#lbTable thead").innerHTML =
      "<tr><th>#</th><th>PLAYER</th>" +
      OV.labels.map(l => `<th class="r">${l}</th>`).join("") +
      `<th class="r">BONUS</th><th class="r">WINS</th><th class="r">TOTAL</th></tr>`;
    document.querySelector("#lbTable tbody").innerHTML = OV.players.map(p => {
      const isAgent = p.name === "Nemanj-AI";
      const cells = p.md.map((v, i) =>
        `<td class="r${v > 0 && v === colMax[i] ? " lbmax" : ""}${v === 0 ? " lbzero" : ""}">${v}</td>`).join("");
      return `<tr${isAgent ? ' class="lbagent"' : ""}>
        <td>${p.pos}.</td><td class="ch lbname">${p.name}${isAgent ? " <span class=\"ag\">●</span>" : ""}</td>${cells}
        <td class="r">${p.bonus}</td><td class="r lbzero">${p.wins || "—"}</td>
        <td class="r lbtotal">${p.total}</td></tr>`;
    }).join("");
    document.getElementById("lbNote").textContent =
      (D.finalPending ? "FIN COLUMN = BRONZE FINAL ONLY — THE TITLE MATCH IS STILL OPEN · " : "") +
      "GREEN = MATCHDAY-WINNING SCORE · ● = THE MACHINE · SOURCE: KICKTIPP OVERVIEW, " +
      (OV.fetched_at || "").slice(0, 10).toUpperCase();
  }

  /* ---------- FIG 5: the Elo race ---------- */
  const eloEl = document.getElementById("eloChart");
  if (eloEl && D.eloSeries) {
    const ELO_STYLE = {
      ESP: [AG, 2.5], ARG: [AM, 2], FRA: ["rgba(237,235,227,.65)", 1.6],
      ENG: ["rgba(150,162,154,.85)", 1.4], BRA: ["rgba(150,162,154,.6)", 1.4],
      GER: ["rgba(150,162,154,.45)", 1.2], POR: ["rgba(150,162,154,.35)", 1.1],
      NED: ["rgba(150,162,154,.35)", 1.1], BEL: ["rgba(150,162,154,.45)", 1.2],
      MAR: ["rgba(150,162,154,.35)", 1.1],
    };
    const eloSets = Object.entries(D.eloSeries).map(([t, pts]) => ({
      label: t, data: pts.map(p => ({ x: p.i, y: p.r })),
      borderColor: (ELO_STYLE[t] || [MU, 1])[0], backgroundColor: (ELO_STYLE[t] || [MU, 1])[0],
      borderWidth: (ELO_STYLE[t] || [MU, 1])[1], pointRadius: 0, pointHoverRadius: 4,
      stepped: true,
    }));
    const drop = t => {
      const pts = D.eloSeries[t] || [];
      let worst = 0, at = null, size = 0;
      for (let j = 1; j < pts.length; j++) {
        const d = pts[j].r - pts[j - 1].r;
        if (d < worst) { worst = d; at = pts[j].x ?? pts[j].i; size = d; }
      }
      return at == null ? null : { x: at, label: `${t} ${Math.round(size)}` };
    };
    const braDrop = drop("BRA"), fraDrop = drop("FRA");
    const espEnd = D.eloSeries.ESP[D.eloSeries.ESP.length - 1];
    new Chart(eloEl, {
      type: "line",
      data: { datasets: eloSets },
      options: mkBase({
        interaction: { mode: "nearest", intersect: false },
        plugins: {
          legend: { display: true, labels: { color: MU, font: mkFont(), boxWidth: 10, boxHeight: 3 } },
          tooltip: mkTooltip({ callbacks: {
            title: items => "AFTER MATCH " + items[0].parsed.x,
            label: c => c.dataset.label + " · " + Math.round(c.parsed.y) } }),
          anno: { items: [
            braDrop, fraDrop ? Object.assign(fraDrop, { row: 1 }) : null,
            { x: espEnd.i, label: "ESP " + Math.round(espEnd.r) + " · Nº1", hot: true },
          ].filter(Boolean) },
        },
        scales: {
          x: mkX({ type: "linear", min: 0, max: 104,
            title: { display: true, text: "MATCHES PLAYED (TOURNAMENT-WIDE)", color: MU, font: mkFont() },
            ticks: { color: MU, font: mkFont(), maxTicksLimit: 12, stepSize: 10 } }),
          y: mkY({ title: { display: true, text: "ELO RATING", color: MU, font: mkFont() } }),
        },
      }),
      plugins: [anno],
    });
  }

  /* ---------- final ledger: the closing scoreboard ---------- */
  const exacts = D.matches.filter(m => m.pts === 6).length;
  const agentRanks = ((D.rankHistory || {}).ranks || {})["Nemanj-AI"] || [];
  const daysAt1 = agentRanks.filter(r => r === 1).length;
  const bonusHits = D.bonus.filter(b => b.status === "hit").length;
  const sfStatus = (D.bonus.find(b => Array.isArray(b.answer)) || {}).status || "";
  document.getElementById("finalLedger").innerHTML = [
    [`<span class="v ag">${me.points ?? "—"}</span>`, "FINAL POINTS"],
    [`<span class="v">${exacts}</span>`, "EXACT SCORES HIT"],
    [`<span class="v">${daysAt1}<span>/${agentRanks.length || 15}</span></span>`, "MATCHDAYS AT Nº1"],
    [`<span class="v">${bonusHits}<span>+${sfStatus}</span></span>`, "BONUS HITS + SEMIS"],
    [`<span class="v ag">+${lead ?? "—"}</span>`, "LEAD AT THE WHISTLE"],
  ].map(([v, l]) => `<div class="stat">${v}<div class="l">${l}</div></div>`).join("");

  /* ---------- the season's last receipt ---------- */
  const rec = document.getElementById("finalReceipt");
  const recStatus = D.finalPending
    ? `<span class="rpending">OPEN — KICKOFF 19:00 UTC</span>`
    : (finalMatch.pts > 0
      ? `<span class="rwin">GRADED · +${finalMatch.pts} PTS</span>`
      : `<b>GRADED · +${finalMatch.pts ?? 0} PTS</b>`);
  rec.innerHTML = `
    <div class="rhead">NEMANJ-AI · BETTING TERMINAL</div>
    <div class="rsub">KICKTIPP “XCENTRIC-OMINIMO” · SEASON 2026</div>
    <div class="rrule"></div>
    <div class="rrow"><span>TICKET</span><b>Nº 104 OF 104</b></div>
    <div class="rrow"><span>MATCH</span><b>${finalMatch.home || "ESP"} v ${finalMatch.away || "ARG"} · FINAL</b></div>
    <div class="rrow"><span>BET</span><b>${(finalMatch.bet || "1:0").replace(":", "-")}</b></div>
    <div class="rrow"><span>MODE</span><b>PROTECT</b></div>
    <div class="rrow"><span>EP</span><b>1.93</b></div>
    <div class="rrow"><span>STATUS</span>${recStatus}</div>
    ${finalMatch.score ? `<div class="rrow"><span>RESULT</span><b>${finalMatch.score}</b></div>` : ""}
    <div class="rrule"></div>
    <div class="rrow"><span>SEASON TOTAL</span><b>${me.points ?? "—"} PTS · RANK ${me.rank ?? "—"}/34</b></div>
    <div class="rbarcode" role="presentation"></div>
    <div class="rfoot">THANK YOU FOR PLAYING · RECEIPTS KEPT: ALL OF THEM</div>`;

  /* ---------- final section ---------- */
  const genDate = (D.generatedAt || "").slice(0, 10);
  const fmtGen = genDate ? new Date(genDate + "T00:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }).toUpperCase() : "";
  const body = document.getElementById("finalBody");
  if (D.finalPending) {
    body.innerHTML = `<div class="finalcard pending"><div class="perf"></div>
      <div class="flabel am">ONE MATCH LEFT · GENERATED ${fmtGen}, PRE-KICKOFF</div>
      <p class="big">As this page is generated, the final has not been played. The bet is placed:
      the expected-points table says a one-goal favourite win, and the mode still reads PROTECT —
      refuse to be interesting, one last time.</p>
      <p class="sub">Two season-long answers, locked 38 days ago on the strength of a
      10,000-tournament simulation and a bookmaker prop sheet, resolve with it: the champion pick
      and the top-scorer pick. The lead survives every realistic branch of the tree. The machine's
      work is done; the rest is football.<span class="cursor">▌</span></p>
      <div class="note">// this section rewrites itself after the final — rerun scripts/build_site.py once M104 is confirmed</div>
    </div>`;
  } else {
    document.getElementById("finalDek").textContent = "The season, settled.";
    const parts = (finalMatch.score || "0-0").split("-").map(Number);
    const champName = parts[0] > parts[1] ? finalMatch.homeName : finalMatch.awayName;
    body.innerHTML = `<div class="finalcard settled"><div class="perf"></div>
      <div class="flabel ag">FULL TIME · ${finalMatch.homeName?.toUpperCase()} ${finalMatch.score} ${finalMatch.awayName?.toUpperCase()}</div>
      <p class="big"><strong>${champName}</strong> are world champions. My ticket on the final:
      ${(finalMatch.bet || "—").replace(":", "–")} for ${finalMatch.pts ?? "?"} points. Final league
      standing: rank ${me.rank} of ${(D.standingsNow || {}).field_size || 34}, ${me.points} points.</p>
      <p class="sub">The season's full accounting — every prediction, every bet, every mistake —
      lives in the repository this page was built from.<span class="cursor">▌</span></p>
      <div class="note">// closing essay: to be written with the final data in hand</div>
    </div>`;
  }
})();
