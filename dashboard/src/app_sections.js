/* GBCA Dashboard, part 4 of 4: sections 2.0-4.0 (sample), the issue log page and wiring. */

function renderNPS(i, p) {
  const n = nps(i), np = p != null ? nps(p) : null;
  $("#nps-pill").innerHTML = pill(status(n.score, D.nps.target, 8));
  $("#nps-value").textContent = signed(n.score);
  $("#nps-delta").innerHTML = delta(n.score, np && np.score, { fmt: pts });
  $("#nps-sub").textContent = `${n.n} responses in the 90 days to ${longDate(D.weeks[i].end)} · Target ${signed(D.nps.target)}`;
  const seg = [["seg-d", "Detractors", n.d], ["seg-pa", "Passives", n.pa], ["seg-p", "Promoters", n.p]];
  const ppd = $("#nps-ppd");
  ppd.setAttribute("aria-label", seg.map(s => `${s[1]} ${Math.round(100 * s[2] / n.n)}%`).join(", "));
  ppd.innerHTML = seg.map(s => `<span class="${s[0]}" style="flex:${s[2]} 1 0"></span>`).join("");
  $("#nps-key").innerHTML = seg.map(s => `<span><i class="${s[0]}"></i>${s[1]} <b>${Math.round(100 * s[2] / n.n)}%</b> (${s[2]})</span>`).join("");
  setTableInto("#nps-class", [{ label: "Class" }, { label: "NPS", num: 1 }, { label: "Change", num: 1 }, { label: "Responses", num: 1 }],
    C.map(c => { const a = nps(i, c), b = p != null ? nps(p, c) : null;
      return [`<strong>${esc(c)}</strong>`, `<strong>${signed(a.score)}</strong>`, delta(a.score, b && b.score, { fmt: pts, suffix: "" }), a.n]; }));
  const vals = D.weeks.map((_, k) => nps(k).score);
  trendChart($("#nps-chart"), { values: vals, height: 250, axes: true, target: D.nps.target, targetLabel: `Target ${signed(D.nps.target)}`,
    step: 5, tick: t => signed(t), fmt: v => signed(v), aria: `Rolling NPS by week, from ${signed(vals[0])} in ${wk(0)} to ${signed(vals[N - 1])} in ${wk(N - 1)}`,
    tipRows: k => { const x = nps(k); return [{ value: signed(x.score), label: `NPS · ${x.n} responses` }, { value: `${Math.round(100 * x.p / x.n)}% / ${Math.round(100 * x.d / x.n)}%`, label: "promoters / detractors" }]; } });
  setTable("#nps-data", [{ label: "Week" }, { label: "NPS", num: 1 }, { label: "Promoters", num: 1 }, { label: "Passives", num: 1 }, { label: "Detractors", num: 1 }, { label: "Responses", num: 1 }],
    D.weeks.map((_, k) => { const x = nps(k); return [wkTitle(k), signed(x.score), x.p, x.pa, x.d, x.n]; }).reverse());
}
function renderValue(i, p) {
  const v = multiple(i), vp = p != null ? multiple(p) : null;
  $("#val-pill").innerHTML = pill(status(v, D.value.target, .5));
  $("#val-value").textContent = times(v);
  $("#val-delta").innerHTML = delta(v, vp, { fmt: x => x.toFixed(2) + "×" });
  $("#val-sub").textContent = `${moneyFull(valueYTD(i))} value delivered ÷ ${moneyFull(duesYTD(i))} dues recognized YTD · Target ${times(D.value.target)}`;
  const cm = C.map(c => ({ label: c, value: multiple(i, c),
    tip: [{ value: times(multiple(i, c)), label: "value-to-dues" }, { value: money(valueYTD(i, c)), label: `value on ${money(duesYTD(i, c))} dues` }] }));
  hbars($("#val-class"), cm, { fmt: times, ref: 1, max: Math.max(4, ...cm.map(r => r.value)) });
  const w = D.value.worthDues[i], wp = p != null ? D.value.worthDues[p] : null;
  $("#val-worth").innerHTML = `<strong>${pct(w, 0)}</strong> of surveyed members agree membership is worth the dues (${D.value.worthDuesN[i]} responses, rolling 90 days). ${delta(r1(w), wp != null ? r1(wp) : null, { fmt: x => pts(Math.round(x)) })}`;
  const rows = streams.map(s => ({ label: s, value: D.value.streamYTD[s][i] })).sort((a, b) => b.value - a.value);
  const tot = valueYTD(i);
  rows.forEach(r => { r.tip = [{ value: moneyFull(r.value), label: "YTD" }, { value: pct(r.value / tot), label: "of value delivered" }]; });
  $("#val-stream-sub").textContent = `${money(tot)} total through ${wk(i)}`;
  hbars($("#val-streams"), rows, { fmt: money });
  setTable("#val-data", [{ label: "Program" }, { label: "Value YTD", num: 1 }, { label: "Share", num: 1 }, { label: "Added this week", num: 1 }],
    rows.map(r => [esc(r.label), moneyFull(r.value), pct(r.value / tot), p != null ? moneyFull(r.value - D.value.streamYTD[r.label][p]) : "—"]),
    ["Total", moneyFull(tot), "100.0%", p != null ? moneyFull(tot - valueYTD(p)) : "—"]);
}

function renderIssues(i) {
  const M = monthCtx(i), cur = period(M.ms, M.asOf), prv = period(M.pms, M.cmpEnd);
  const vs = { suffix: ` vs ${M.cmpLabel}` };
  $("#iss-lede").innerHTML = `Are we closing member issues as fast as they arrive, and what did resolution save members? Reported by calendar month: <strong>${esc(M.label)}</strong> through ${dshort(M.asOf)}, compared with ${esc(M.cmpLabel)}.`;
  const cy = sumCost(resolvedIn(M.y0, M.asOf)), pace = costPace(M);
  const stats = [
    ["Opened", cur.opened, delta(cur.opened, prv.opened, vs).replace(/ d-(good|bad)/, "")],
    ["Resolved", cur.resolved, delta(cur.resolved, prv.resolved, vs)],
    ["Open now", cur.backlog, delta(cur.backlog, prv.backlog, { goodUp: false, suffix: ` vs ${dshort(M.cmpEnd)}` })],
    ["Median days", fmtDays(cur.med), `<span class="delta">Target ≤ ${D.issues.medianDaysTarget} days</span>`],
    [`Avoided in ${M.short}`, money(cur.cost), delta(cur.cost, prv.cost, { fmt: money, ...vs })],
    ["Avoided YTD", money(cy), `<span class="delta">Pace ${money(pace)}</span>`],
  ];
  $("#iss-stats").innerHTML = stats.map(s => `<div class="stat"><div class="k">${esc(s[0])}</div><div class="v">${s[1]}</div>${s[2]}</div>`).join("");

  const per = M.months.map(mo => period(mo.a, mo.b));
  const labels = M.months.map(mo => MONTHS[mo.k] + (mo.partial ? "*" : ""));
  const moTitle = k => `${FULLMONTHS[M.months[k].k]} ${M.y}` + (M.months[k].partial ? `, to ${dshort(M.months[k].b)}` : "");
  $("#iss-chart-sub").textContent = `January to ${FULLMONTHS[M.m]} ${M.y}`;
  columnChart($("#iss-chart"), { height: 230, labels, sel: per.length - 1,
    series: [{ values: per.map(x => x.opened), cls: "bar-a" }, { values: per.map(x => x.resolved), cls: "bar-b" }],
    aria: `Issues opened and resolved by month, January to ${FULLMONTHS[M.m]} ${M.y}`, tipTitle: moTitle,
    tipRows: k => [{ key: "tk-b", value: String(per[k].resolved), label: "resolved" }, { key: "tk-a", value: String(per[k].opened), label: "opened" },
                   { value: String(per[k].backlog), label: M.months[k].partial ? `open on ${dshort(per[k].b)}` : "open at month end" },
                   { value: money(per[k].cost), label: "cost avoided" }] });
  $("#iss-chart-note").textContent = M.partial ? `* ${FULLMONTHS[M.m]} is month to date through ${dshort(M.asOf)}.` : "";
  setTable("#iss-data", [{ label: "Month" }, { label: "Opened", num: 1 }, { label: "Resolved", num: 1 }, { label: "Open at month end", num: 1 }, { label: "Median days", num: 1 }, { label: "Cost avoided", num: 1 }],
    per.map((x, k) => [esc(moTitle(k)), x.opened, x.resolved, x.backlog, fmtDays(x.med), moneyFull(x.cost)]).reverse(),
    ["Year to date", per.reduce((s, x) => s + x.opened, 0), per.reduce((s, x) => s + x.resolved, 0), cur.backlog,
     fmtDays(median(resolvedIn(M.y0, M.asOf).map(x => x.days))), moneyFull(cy)]);

  const cats = {};
  for (const c of D.issues.categories) cats[c] = 0;
  for (const x of resolvedIn(M.y0, M.asOf)) cats[x.cat] += x.cost;
  const rows = Object.keys(cats).map(c => ({ label: c, value: cats[c], tip: [{ value: moneyFull(cats[c]), label: "avoided YTD" }, { value: pct(cats[c] / cy), label: "of total" }] })).sort((a, b) => b.value - a.value);
  $("#cat-sub").textContent = `${money(cy)} through ${dshort(M.asOf)} against a ${money(D.issues.annualCostTarget)} annual goal`;
  hbars($("#iss-cats"), rows, { fmt: money });
  setTable("#cat-data", [{ label: "Issue type" }, { label: "Avoided YTD", num: 1 }, { label: "Share", num: 1 }],
    rows.map(r => [esc(r.label), moneyFull(r.value), pct(r.value / cy)]), ["Total", moneyFull(cy), "100.0%"]);

  $("#log-teaser").textContent = `${cur.resolved} issues resolved in ${M.label}, ${moneyFull(cur.cost)} cost avoided, ${cur.basis} with a dollar basis. The issue-by-issue list opens on its own page.`;
  $("#open-log").innerHTML = `Open the ${esc(MONTHS[M.m])} issue log <span aria-hidden="true">→</span>`;
}

const LOG_COLS = [
  { key: "id", label: "Issue", get: x => x.id, cell: x => `<strong>${esc(x.id)}</strong>` },
  { key: "on", label: "Opened", get: x => x.on, cell: x => dshort(x.on), cls: "nw" },
  { key: "rn", label: "Resolved", get: x => x.rn, cell: x => dshort(x.rn), cls: "nw" },
  { key: "days", label: "Days", num: 1, get: x => x.days, cell: x => x.days },
  { key: "mem", label: "Member", get: x => x.mem, cell: x => esc(x.mem), cls: "nw" },
  { key: "cls", label: "Class", get: x => x.cls, cell: x => esc(x.cls) },
  { key: "cat", label: "Issue type", get: x => x.cat, cell: x => esc(x.cat) },
  { key: "own", label: "Owner", get: x => x.own, cell: x => esc(x.own) },
  { key: "cost", label: "Cost avoided", num: 1, get: x => x.cost, cell: x => moneyFull(x.cost) },
  { key: "basis", label: "Basis", get: x => x.basis, cell: x => esc(x.basis) },
];
state.sort = { key: "cost", dir: -1 };
function renderLog(i) {
  const M = monthCtx(i), cur = period(M.ms, M.asOf);
  $("#log-lede").innerHTML = `Every issue resolved in <strong>${esc(M.label)}</strong>, through ${dlong(M.asOf)}. Change the week at the top to move between months.`;
  $("#log-stats").className = "stats s-4";
  $("#log-stats").innerHTML = [["Resolved", cur.resolved], ["Cost avoided", moneyFull(cur.cost)], ["With a dollar basis", `${cur.basis} of ${cur.resolved}`], ["Median days", fmtDays(cur.med)]]
    .map(s => `<div class="stat"><div class="k">${s[0]}</div><div class="v">${s[1]}</div></div>`).join("");
  $("#log-title").textContent = `Resolved in ${M.label}`;
  const col = LOG_COLS.find(c => c.key === state.sort.key), dir = state.sort.dir;
  const list = [...cur.res].sort((a, b) => { const va = col.get(a), vb = col.get(b); return (va < vb ? -1 : va > vb ? 1 : 0) * dir || a.on - b.on; });
  const th = LOG_COLS.map(c => `<th${c.num ? ' class="num"' : ""}${c.key === col.key ? ` aria-sort="${dir > 0 ? "ascending" : "descending"}"` : ""}><button type="button" data-sort="${c.key}">${c.label}${c.key === col.key ? (dir > 0 ? " ▲" : " ▼") : ""}</button></th>`).join("");
  const td = x => `<tr>${LOG_COLS.map(c => `<td class="${[c.num ? "num" : "", c.cls || ""].join(" ").trim()}">${c.cell(x)}</td>`).join("")}</tr>`;
  $("#log-table").innerHTML = `<thead><tr>${th}</tr></thead><tbody>${list.map(td).join("")}</tbody>
    <tfoot><tr><td>${list.length} resolved</td><td></td><td></td><td class="num">median ${fmtDays(cur.med)}</td><td></td><td></td><td></td><td></td><td class="num">${moneyFull(cur.cost)}</td><td>${cur.basis} with a dollar basis</td></tr></tfoot>`;
}
$("#log-table").addEventListener("click", e => {
  const b = e.target.closest("button[data-sort]"); if (!b) return;
  const key = b.dataset.sort;
  state.sort = state.sort.key === key ? { key, dir: -state.sort.dir } : { key, dir: LOG_COLS.find(c => c.key === key).num ? -1 : 1 };
  renderLog(state.sel);
  const nb = document.querySelector(`#log-table button[data-sort="${key}"]`); if (nb) nb.focus();
});

/* Page 2: the issue log sits behind a click and replaces the dashboard until "Back". The hash keeps the
   browser's Back button working; if the frame refuses hash changes, the buttons still switch pages. */
function showLog(on) {
  const was = !$("#issue-log").hidden;
  document.querySelector("main").hidden = on;
  $("#issue-log").hidden = !on;
  hideTip();
  if (on) { renderLog(state.sel); window.scrollTo(0, 0); }
  else if (was) { const t = $("#issues"); if (t) t.scrollIntoView(); }
}
function go(on) {
  try { location.hash = on ? "issue-log" : "issues"; } catch (err) { /* sandboxed frame */ }
  if ((location.hash === "#issue-log") !== on) showLog(on);
}
window.addEventListener("hashchange", () => showLog(location.hash === "#issue-log"));
$("#open-log").addEventListener("click", () => go(true));
document.querySelectorAll("[data-back]").forEach(b => b.addEventListener("click", () => go(false)));
/* In-page tiles (Member engagement) scroll to their section without touching the hash. */
$("#kpis").addEventListener("click", e => {
  const a = e.target.closest('a[href^="#"]');
  if (!a) return;
  const t = document.getElementById(a.getAttribute("href").slice(1));
  if (!t) return;
  e.preventDefault();
  t.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
  const h = t.querySelector("h2"); if (h) h.focus({ preventScroll: true });
});

/* ---------- wiring ---------- */
function render() {
  const i = state.sel, p = i > 0 ? i - 1 : null, s = L.eng[i];
  $("#week").value = String(i);
  $("#prev").disabled = i === 0; $("#next").disabled = i === N - 1;
  $("#asof").textContent = `Week ending ${longDate(D.weeks[i].end)} · ${s ? "Engagement as of " + shortDate(s.date) : "No engagement report this week"}`;
  hideTip();
  renderKPIs(i, p); renderAttention(i, p); renderEng(i); renderNPS(i, p); renderValue(i, p); renderIssues(i);
  if (!$("#issue-log").hidden) renderLog(i);
}
$("#week").innerHTML = D.weeks.map((w, k) => `<option value="${k}">${esc(wkTitle(k))}, ${day(w.end).getFullYear()}</option>`).reverse().join("");
$("#week").addEventListener("change", e => select(+e.target.value));
$("#prev").addEventListener("click", () => select(Math.max(0, state.sel - 1)));
$("#next").addEventListener("click", () => select(Math.min(N - 1, state.sel + 1)));
$("#status-key").innerHTML = ["good", "watch", "bad"].map(s => `<li>${icon(s)}${STATUS[s]}</li>`).join("");
document.querySelectorAll(".data-btn").forEach(b => b.addEventListener("click", () => {
  const t = document.getElementById(b.getAttribute("aria-controls")), open = t.hidden;
  t.hidden = !open; b.setAttribute("aria-expanded", String(open)); b.textContent = open ? (b.dataset.hide || "Hide data") : (b.dataset.show || "View data");
}));
let lastW = 0, raf = 0;
new ResizeObserver(entries => {
  const w = Math.round(entries[0].contentRect.width);
  if (w === lastW) return; lastW = w;
  cancelAnimationFrame(raf); raf = requestAnimationFrame(render);
}).observe(document.querySelector("main"));
$("#built").textContent = `Version 1.0 · Built ${shortDate(L.built)}${L.latest ? " from the engagement report of " + shortDate(L.latest.date) : ""}.`;
render();
if (location.hash === "#issue-log") showLog(true);
window.GBCA_READY = true;
