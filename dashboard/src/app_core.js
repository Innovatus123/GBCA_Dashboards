/* GBCA Dashboard, part 1 of 4: data, formatting, metrics, status and SVG helpers.
   GBCA_LIVE comes from the weekly build (build_dashboard.py): the 13-week calendar, the live engagement
   counts from the GrowthZone engagement report, links and targets. GBCA_SAMPLE is the layout sample behind
   sections 2.0-4.0; its weeks are moved onto the live calendar so the week control scopes every section. */
const L = window.GBCA_LIVE, S = window.GBCA_SAMPLE;
const C = L.classes, N = L.weeks.length;
const $ = s => document.querySelector(s);
const MINUS = "−";
const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const FULLMONTHS = ["January","February","March","April","May","June","July","August","September","October","November","December"];
const esc = s => String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const dnum = s => Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10)) / 864e5;
const ddate = n => new Date(n * 864e5);
const SHIFT = dnum(L.weeks[N - 1].start) - dnum(S.weeks[S.weeks.length - 1].start);
const iso = n => ddate(n).toISOString().slice(0, 10);
const D = {
  weeks: L.weeks.map((w, k) => ({ ...w, swk: S.weeks[k].wk })),
  nps: S.nps, value: S.value,
  issues: { ...S.issues, through: iso(dnum(S.issues.through) + SHIFT),
    log: S.issues.log.map((r, k) => ({ id: "ISS-26-" + String(k + 1).padStart(4, "0"), o: iso(r[0] + SHIFT),
      r: r[1] < 0 ? null : iso(r[0] + r[1] + SHIFT), cls: C[r[2]], mem: "M-" + r[3], cat: S.issues.categories[r[4]],
      own: S.issues.owners[r[5]], cost: r[6], basis: S.issues.bases[r[7]] })) },
};
const state = { sel: N - 1 };

/* ---------- formatting ---------- */
const signed = (v, d = 0) => (v > 0 ? "+" : v < 0 ? MINUS : "") + Math.abs(v).toFixed(d);
const pct = (v, d = 1) => (v * 100).toFixed(d) + "%";
const money = v => {
  const a = Math.abs(v);
  if (a >= 1e6) return "$" + (v / 1e6).toFixed(2) + "M";
  if (a >= 1e5) return "$" + Math.round(v / 1e3) + "K";
  if (a >= 1e3) return "$" + (v / 1e3).toFixed(1) + "K";
  return "$" + Math.round(v).toLocaleString("en-US");
};
const moneyFull = v => "$" + Math.round(v).toLocaleString("en-US");
const times = v => v.toFixed(2) + "×";
const pts = v => v + (v === 1 ? " pt" : " pts");
const day = s => new Date(s + "T00:00:00");
function span(w) {
  const a = day(w.start), b = day(w.end);
  return a.getMonth() === b.getMonth()
    ? `${MONTHS[a.getMonth()]} ${a.getDate()}–${b.getDate()}`
    : `${MONTHS[a.getMonth()]} ${a.getDate()} – ${MONTHS[b.getMonth()]} ${b.getDate()}`;
}
const wk = i => "W" + D.weeks[i].wk;
const wkTitle = i => `Week ${D.weeks[i].wk} · ${span(D.weeks[i])}`;
const longDate = s => { const d = day(s); return `${["Sun","Mon","Tue","Wed","Thu","Fri","Sat"][d.getDay()]} ${MONTHS[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`; };
const shortDate = s => { const d = day(s); return `${MONTHS[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`; };

/* ---------- live engagement (section 1.0, member count) ----------
   Each live week holds the five scorecard bands per class, in the order Highly Engaged, Engaged,
   Low Risk, Moderate Risk, High Risk. The roll-up combines them into Engaged, Low Risk and Risk. */
const BANDS = [["eng", "Engaged", "e"], ["low", "Low Risk", "l"], ["risk", "Risk", "r"]];
const LEVELS = ["Highly Engaged", "Engaged", "Low Risk", "Moderate Risk", "High Risk"];
function levels(i, c) {
  const s = L.eng[i];
  if (!s) return null;
  return c ? s.c[c] : C.reduce((t, k) => t.map((v, j) => v + s.c[k][j]), [0, 0, 0, 0, 0]);
}
function eng(i, c) {
  const a = i == null ? null : levels(i, c);
  if (!a) return null;
  const n = a.reduce((x, y) => x + y, 0);
  return { eng: a[0] + a[1], low: a[2], risk: a[3] + a[4], n, a };
}
const share = (e, k) => e.n ? e[k] / e.n : 0;
const r1 = v => Math.round(v * 1000) / 10;              // rate -> percent, 1 dp, as displayed
const liveWeeks = L.eng.map((s, k) => s ? k : -1).filter(k => k >= 0);
const firstLive = liveWeeks.length ? liveWeeks[0] : null;
/* The OneDrive copies open best from the synced "0 - GBCA SharePoint/Dashboards" folder, where the
   relative path reaches the component directly; anywhere else (the Box copy, a download) uses the OneDrive web link. */
const inSyncedFolder = (() => { try { return location.protocol === "file:" && decodeURIComponent(location.pathname).includes(L.syncRoot); } catch (e) { return false; } })();
const link = k => inSyncedFolder ? encodeURI(L.links[k].rel) : L.links[k].web;

/* ---------- sample metrics (sections 2.0-4.0) ---------- */
function nps(i, cls) {
  let p = 0, pa = 0, d = 0;
  for (const c of cls ? [cls] : C) { const r = D.nps.counts[c][i]; p += r[0]; pa += r[1]; d += r[2]; }
  const n = p + pa + d;
  return { p, pa, d, n, score: Math.round(100 * (p - d) / n) };
}
const streams = Object.keys(D.value.streamYTD);
const valueYTD = (i, c) => c ? D.value.classYTD[c][i] : streams.reduce((s, k) => s + D.value.streamYTD[k][i], 0);
const annualDues = c => c ? D.value.annualDues[c] : C.reduce((s, k) => s + D.value.annualDues[k], 0);
const duesYTD = (i, c) => annualDues(c) * D.weeks[i].swk / 52;
const multiple = (i, c) => Math.round(100 * valueYTD(i, c) / duesYTD(i, c)) / 100;
const median = a => { if (!a.length) return 0; const s = [...a].sort((x, y) => x - y), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
/* Issues come from a dated log (one row per issue), the same rows as the Excel workbook.
   Dates become UTC day numbers so any window (month, month to date, year to date) is a range test. */
const dshort = n => `${MONTHS[ddate(n).getUTCMonth()]} ${ddate(n).getUTCDate()}`;
const dlong = n => `${MONTHS[ddate(n).getUTCMonth()]} ${ddate(n).getUTCDate()}, ${ddate(n).getUTCFullYear()}`;
const LOG = D.issues.log.map(x => {
  const on = dnum(x.o), rn = x.r ? dnum(x.r) : null;
  return { ...x, on, rn, days: rn == null ? null : rn - on };
});
const openedIn = (a, b) => LOG.filter(x => x.on >= a && x.on <= b);
const resolvedIn = (a, b) => LOG.filter(x => x.rn != null && x.rn >= a && x.rn <= b);
const backlogAt = t => LOG.filter(x => x.on <= t && (x.rn == null || x.rn > t)).length;
const sumCost = list => list.reduce((s, x) => s + x.cost, 0);
function period(a, b) {
  const res = resolvedIn(a, b);
  return { a, b, opened: openedIn(a, b).length, resolved: res.length, res, med: median(res.map(x => x.days)),
           cost: sumCost(res), basis: res.filter(x => x.cost > 0).length, backlog: backlogAt(b) };
}
/* The month shown in 4.0 is the one the selected week ends in, month to date through that day.
   The comparison is the same days of the prior month, so a partial month is never set against a full one. */
function monthCtx(i) {
  const asOf = dnum(D.weeks[i].end), dt = ddate(asOf), y = dt.getUTCFullYear(), m = dt.getUTCMonth();
  const dm = (yy, mm, dd) => Date.UTC(yy, mm, dd) / 864e5;
  const ms = dm(y, m, 1), me = dm(y, m + 1, 0), partial = asOf < me;
  const pms = dm(y, m - 1, 1), pme = dm(y, m, 0), cmpEnd = partial ? Math.min(pme, pms + (asOf - ms)) : pme;
  const pm = (m + 11) % 12;
  const months = [];
  for (let k = 0; k <= m; k++) {
    const end = dm(y, k + 1, 0);
    months.push({ k, a: dm(y, k, 1), b: Math.min(end, asOf), partial: asOf < end });
  }
  return { i, asOf, y, m, ms, partial, pms, cmpEnd, y0: dm(y, 0, 1), yearDays: dm(y + 1, 0, 1) - dm(y, 0, 1), months,
    short: MONTHS[m] + (partial ? " MTD" : ""),
    label: partial ? `${FULLMONTHS[m]} ${y}, month to date` : `${FULLMONTHS[m]} ${y}`,
    cmpLabel: partial ? `${MONTHS[pm]} 1–${ddate(cmpEnd).getUTCDate()}` : FULLMONTHS[pm] };
}
const costPace = M => D.issues.annualCostTarget * (M.asOf - M.y0 + 1) / M.yearDays;
const fmtDays = v => v ? (Number.isInteger(v) ? String(v) : v.toFixed(1)) : "—";

/* ---------- status ---------- */
const STATUS = { good: "On track", watch: "Watch", bad: "Off track", none: "No target" };
function status(v, target, tol, higherIsBetter = true) {
  if (target == null) return "none";
  const gap = higherIsBetter ? v - target : target - v;
  return gap >= 0 ? "good" : gap >= -tol ? "watch" : "bad";
}
const worst = (...s) => s.includes("bad") ? "bad" : s.includes("watch") ? "watch" : "good";
function icon(s) {
  const glyph = s === "good" ? '<path class="gl" d="M4.2 7.3l1.9 1.9 3.8-4"/>'
    : s === "watch" ? '<path class="gl-w" d="M7 3.6v4.1M7 10.1v.2"/>'
    : s === "none" ? '<path class="gl" d="M4.3 7h5.4"/>'
    : '<path class="gl" d="M4.8 4.8l4.4 4.4M9.2 4.8l-4.4 4.4"/>';
  return `<svg class="ic" viewBox="0 0 14 14" aria-hidden="true"><circle class="bg-${s}" cx="7" cy="7" r="7"/>${glyph}</svg>`;
}
const pill = s => `<span class="pill">${icon(s)}${STATUS[s]}</span>`;
const TAG = { live: '<span class="tag live">Live</span>', sample: '<span class="tag sample">Sample</span>' };

function delta(cur, prev, { fmt = v => v, goodUp = true, neutral = false, suffix = " vs prior week", none = "No prior week in view", same = "No change" } = {}) {
  if (prev == null) return `<span class="delta">${esc(none)}</span>`;
  const dv = Math.round((cur - prev) * 1e6) / 1e6;
  if (dv === 0) return `<span class="delta">${esc(same)}${esc(suffix)}</span>`;
  const good = goodUp ? dv > 0 : dv < 0;
  return `<span class="delta${neutral ? "" : good ? " d-good" : " d-bad"}"><b>${dv > 0 ? "▲" : "▼"} ${esc(fmt(Math.abs(dv)))}</b>${esc(suffix)}</span>`;
}

/* ---------- tooltip ---------- */
const tip = $("#tip");
function showTip(evt, title, rows) {
  tip.replaceChildren();
  const h = document.createElement("div"); h.className = "tip-h"; h.textContent = title; tip.appendChild(h);
  for (const r of rows) {
    const row = document.createElement("div"); row.className = "tip-r";
    if (r.key) { const k = document.createElement("span"); k.className = "tip-k " + r.key; row.appendChild(k); }
    const v = document.createElement("strong"); v.textContent = r.value; row.appendChild(v);
    if (r.label) row.appendChild(document.createTextNode(" " + r.label));
    tip.appendChild(row);
  }
  tip.hidden = false;
  const pad = 14, b = tip.getBoundingClientRect();
  let x = evt.clientX + pad, y = evt.clientY + pad;
  if (x + b.width > innerWidth - 8) x = evt.clientX - b.width - pad;
  if (y + b.height > innerHeight - 8) y = evt.clientY - b.height - pad;
  tip.style.left = Math.max(8, x) + "px"; tip.style.top = Math.max(8, y) + "px";
}
const hideTip = () => { tip.hidden = true; };

/* ---------- SVG helpers ---------- */
const NS = "http://www.w3.org/2000/svg";
function el(tag, attrs, parent) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}
function niceStep(range, ticks = 4) {
  const raw = Math.max(range, 1e-9) / ticks, mag = Math.pow(10, Math.floor(Math.log10(raw)));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * mag >= raw) return m * mag;
  return 10 * mag;
}
function barPath(x, base, w, h) {
  if (h <= 0) return "";
  const r = Math.min(4, w / 2, h), t = base - h;
  return `M${x},${base}V${t + r}Q${x},${t} ${x + r},${t}H${x + w - r}Q${x + w},${t} ${x + w},${t + r}V${base}Z`;
}
function select(i) { if (i !== state.sel) { state.sel = i; render(); } }
