/* GBCA Dashboard, part 3 of 4: the bottom line, needs-attention list and section 1.0 (live). */

/* The latest earlier week with a live report, so one missed Saturday run still yields a comparison. */
function prevLive(i) { for (let k = i - 1; k >= 0; k--) if (L.eng[k]) return k; return null; }
const sinceText = (i, k) => k === i - 1 ? "last week" : wk(k);
const noPrev = i => ({ none: i === firstLive ? "First live week" : "No earlier live week" });

function renderKPIs(i, p) {
  const n = nps(i), np = p != null ? nps(p) : null;
  const v = multiple(i), vp = p != null ? multiple(p) : null;
  const M = monthCtx(i), cur = period(M.ms, M.asOf), prv = period(M.pms, M.cmpEnd);
  const cy = sumCost(resolvedIn(M.y0, M.asOf)), pace = costPace(M);
  const vs = { suffix: ` vs ${M.cmpLabel}` };
  const sIss = worst(cur.backlog <= prv.backlog ? "good" : cur.backlog - prv.backlog <= 3 ? "watch" : "bad",
                     status(cur.med, D.issues.medianDaysTarget, 3, false));
  const k = prevLive(i), e = eng(i), ep = eng(k), T = L.targets.All;
  const cmp = ep ? { suffix: k === i - 1 ? " vs prior week" : ` vs ${wk(k)}` } : noPrev(i);
  const noLive = `<span class="delta">No live report this week</span>`;
  const tiles = [
    { label: "Member count", tag: "live", href: link("map"), ext: true, go: "↗", sr: "opens the GBCA Member Map",
      value: e ? String(e.n) : "—", d: e ? delta(e.n, ep && ep.n, cmp) : noLive,
      sub: e ? C.map(c => `${esc(c)} ${eng(i, c).n}`).join(" · ") : `Latest report ${L.latest ? shortDate(L.latest.date) : "not yet available"}`,
      foot: `<span>${e ? "GrowthZone, " + shortDate(L.eng[i].date) : "No report this week"}</span><span>Open member map</span>` },
    { label: "Member engagement", tag: "live", href: "#engagement", go: "↓", sr: "goes to section 1.0",
      value: e ? pct(share(e, "eng")) : "—",
      d: e ? delta(r1(share(e, "eng")), ep && r1(share(ep, "eng")), { fmt: x => x.toFixed(1) + " pts", ...cmp }) : noLive,
      sub: e ? `${e.eng} of ${e.n} engaged · ${e.risk} at risk (${pct(share(e, "risk"))})` : "Section 1.0 shows the weeks with data",
      foot: `<span>${T == null ? "Target pending sign-off" : "Target " + pct(T, 0)}</span>${pill(e ? status(share(e, "eng"), T, .05) : "none")}` },
    { label: "Net Promoter Score", tag: "sample", value: signed(n.score), d: delta(n.score, np && np.score, { fmt: pts }),
      sub: `Rolling 90 days · ${n.n} responses`, foot: `<span>Target ${signed(D.nps.target)}</span>${pill(status(n.score, D.nps.target, 8))}` },
    { label: "Member value", tag: "sample", value: times(v), d: delta(v, vp, { fmt: x => x.toFixed(2) + "×" }),
      sub: `${money(valueYTD(i))} delivered on ${money(duesYTD(i))} dues YTD`, foot: `<span>Target ${times(D.value.target)}</span>${pill(status(v, D.value.target, .5))}` },
    { label: `Issues resolved · ${M.short}`, tag: "sample", value: String(cur.resolved), d: delta(cur.resolved, prv.resolved, vs),
      sub: `${cur.opened} opened · ${cur.backlog} still open · median ${fmtDays(cur.med)} days`,
      foot: `<span>Backlog ${cur.backlog < prv.backlog ? "falling" : cur.backlog > prv.backlog ? "rising" : "flat"}</span>${pill(sIss)}` },
    { label: `Cost avoidance · ${M.short}`, tag: "sample", value: money(cur.cost), d: delta(cur.cost, prv.cost, { fmt: money, ...vs }),
      sub: `${money(cy)} year to date`, foot: `<span>Pace ${money(pace)} YTD</span>${pill(status(cy, pace, pace * .1))}` },
  ];
  $("#kpis").innerHTML = tiles.map(t => {
    const go = t.go ? `<span class="kpi-go"><span aria-hidden="true">${t.go}</span><span class="sr-only">, ${t.sr}</span></span>` : "";
    const body = `<div class="kpi-label">${t.label}${TAG[t.tag]}${go}</div><div class="kpi-value">${t.value}</div><div class="kpi-delta">${t.d}</div><div class="kpi-sub">${t.sub}</div><div class="kpi-foot">${t.foot}</div>`;
    return t.href ? `<a class="kpi" href="${esc(t.href)}"${t.ext ? ' target="_blank" rel="noopener"' : ""}>${body}</a>` : `<div class="kpi">${body}</div>`;
  }).join("");
}

function renderAttention(i, p) {
  const live = [], items = [];
  const e = eng(i), k = prevLive(i), ep = eng(k);
  if (!e && i === N - 1)
    live.push(["watch", `<strong>No live engagement report this week.</strong> ${L.latest ? `The latest is from ${shortDate(L.latest.date)}.` : ""} Check the Saturday GrowthZone run.`]);
  if (e) {
    for (const c of C) {
      const x = eng(i, c), xp = eng(k, c), rs = share(x, "risk"), T = L.targets[c], s = status(share(x, "eng"), T, .05);
      if (s === "bad" || s === "watch") live.push([s, `<strong>${esc(c)} engagement at ${pct(share(x, "eng"))}</strong> against a ${pct(T, 0)} target.`]);
      if (rs > L.riskAlert) live.push(["bad", `<strong>${esc(c)}: ${x.risk} of ${x.n} members at Risk</strong> (${pct(rs)}). ${x.eng} ${x.eng === 1 ? "is" : "are"} Engaged.`]);
      if (xp) {
        const d = Math.round(10 * (r1(rs) - r1(share(xp, "risk")))) / 10;
        if (d >= 1) live.push([d >= 3 ? "bad" : "watch", `<strong>${esc(c)} Risk share up ${d.toFixed(1)} pts</strong> since ${sinceText(i, k)}, to ${pct(rs)} (${x.risk} members).`]);
      }
    }
    if (ep && e.eng < ep.eng) live.push(["watch", `<strong>Engaged members down ${ep.eng - e.eng}</strong> since ${sinceText(i, k)}, to ${e.eng} of ${e.n}.`]);
  }
  const n = nps(i), sN = status(n.score, D.nps.target, 8);
  if (sN !== "good") items.push([sN, `<strong>NPS at ${signed(n.score)}</strong> against a ${signed(D.nps.target)} target (${n.n} responses, rolling 90 days).`]);
  for (const c of C) {
    if (p != null && nps(p, c).score - nps(i, c).score >= 5)
      items.push(["watch", `<strong>${esc(c)} NPS fell ${nps(p, c).score - nps(i, c).score} pts</strong> to ${signed(nps(i, c).score)} (${nps(i, c).n} responses).`]);
    if (multiple(i, c) < 1) items.push(["bad", `<strong>${esc(c)} value multiple below 1.0×</strong>: measured value is under dues paid.`]);
  }
  const v = multiple(i), sV = status(v, D.value.target, .5);
  if (sV !== "good") items.push([sV, `<strong>Value multiple at ${times(v)}</strong> against a ${times(D.value.target)} target.`]);
  const M = monthCtx(i), cur = period(M.ms, M.asOf), prv = period(M.pms, M.cmpEnd);
  if (cur.backlog > prv.backlog) items.push([cur.backlog - prv.backlog > 3 ? "bad" : "watch", `<strong>Issue backlog at ${cur.backlog}</strong>, up from ${prv.backlog} on ${dshort(M.cmpEnd)} (${cur.opened} opened, ${cur.resolved} resolved in ${esc(M.short)}).`]);
  if (cur.med > D.issues.medianDaysTarget) items.push([status(cur.med, D.issues.medianDaysTarget, 3, false), `<strong>Median resolution time ${fmtDays(cur.med)} days</strong> in ${esc(M.short)} against a ${D.issues.medianDaysTarget}-day target.`]);
  const cy = sumCost(resolvedIn(M.y0, M.asOf)), pace = costPace(M);
  if (cy < pace) items.push([status(cy, pace, pace * .1), `<strong>Cost avoidance behind pace</strong>: ${money(cy)} year to date against ${money(pace)}.`]);
  /* Live findings lead; sample findings follow, each marked so they are never read as GBCA actuals. */
  const bad = a => a.sort((x, y) => (x[0] === "bad" ? 0 : 1) - (y[0] === "bad" ? 0 : 1));
  const all = bad(live).map(x => [...x, ""]).concat(bad(items).map(x => [...x, TAG.sample])).slice(0, 8);
  $("#attn").innerHTML = all.length
    ? all.map(([s, t, tag]) => `<li>${icon(s)}<span><span class="sr-only">${STATUS[s]}: </span>${t}${tag}</span></li>`).join("")
    : `<li>${icon("good")}<span>Nothing is off track or on watch this week.</span></li>`;
}

/* ---------- 1.0 Member Engagement (live) ---------- */
const compBar = x => `<div class="ppd" role="img" aria-label="${BANDS.map(([k, name]) => `${name} ${pct(share(x, k), 0)}`).join(", ")}">${BANDS.map(([k, , c]) => x[k] ? `<span class="seg-${c}" style="flex:${x[k]} 1 0"></span>` : "").join("")}</div>`;
const bandBlocks = (x, xp) => `<div class="bands">${BANDS.map(([k, name, c]) => `<div class="band"><div class="k"><i class="seg-${c}"></i>${name}</div><div class="v">${pct(share(x, k))}</div><div class="c"><span>${x[k]} <span class="n-of">of ${x.n}</span></span>${xp ? delta(x[k], xp[k], { goodUp: k === "eng", neutral: k === "low", suffix: "", same: "±0" }) : ""}</div></div>`).join("")}</div>`;

function renderEng(i) {
  const s = L.eng[i], e = eng(i), k = prevLive(i), ep = eng(k);
  const start = firstLive != null ? ` Live history starts ${wkTitle(firstLive)}.` : "";
  $("#eng-lede").innerHTML = e
    ? `Where members stand on the 2026 engagement scorecards, from the GrowthZone engagement report of ${shortDate(s.date)}. <strong>${e.eng} of ${e.n} members are Engaged (${pct(share(e, "eng"))}) and ${e.risk} are at Risk (${pct(share(e, "risk"))}).</strong> Engaged combines Highly Engaged and Engaged; Risk combines Moderate and High Risk.${ep ? ` Changes are against ${k === i - 1 ? "the prior week" : wkTitle(k)}.` : ""}`
    : `No live engagement report falls in ${esc(wkTitle(i))}.${start}`;
  $("#eng-all-sub").textContent = e ? `${e.n} members · report of ${shortDate(s.date)}` : "No report this week";
  $("#eng-report").href = link("report");
  $("#eng-all-body").innerHTML = e ? bandBlocks(e, ep) + compBar(e) : `<p class="empty">No live report this week.${start}</p>`;
  $("#eng-key").innerHTML = BANDS.map(([, name, c]) => `<span><i class="seg-${c}"></i>${name}</span>`).join("");
  shareCols($("#eng-cols"), { height: 120, axes: true, get: x => eng(x), aria: `Share of members Engaged, Low Risk and at Risk by week, ${liveWeeks.length} weeks with a live report` });

  const cols = [...C, null], lv = c => levels(i, c), ex = c => eng(i, c);
  const withShare = (c, key) => `${ex(c)[key]} <span class="n-of">(${pct(share(ex(c), key))})</span>`;
  const rows = [
    ["Highly Engaged", c => lv(c)[0]], ["Engaged", c => lv(c)[1]],
    ["Engaged, combined", c => withShare(c, "eng"), 1],
    ["Low Risk", c => withShare(c, "low"), 1],
    ["Moderate Risk", c => lv(c)[3]], ["High Risk", c => lv(c)[4]],
    ["Risk, combined", c => withShare(c, "risk"), 1],
    ["Total members", c => ex(c).n, 1],
  ];
  $("#eng-detail").innerHTML = e
    ? `<table><thead><tr><th>Scorecard band</th>${cols.map(c => `<th class="num">${c ? esc(c) : "All members"}</th>`).join("")}</tr></thead><tbody>${rows.map(([name, f, roll]) => `<tr${roll ? ' class="roll"' : ""}><td>${name}</td>${cols.map(c => `<td class="num">${f(c)}</td>`).join("")}</tr>`).join("")}</tbody></table>`
    : `<p class="empty">No report this week.</p>`;

  const box = $("#eng-panels");
  box.innerHTML = C.map(c => {
    const x = eng(i, c), xp = eng(k, c), T = L.targets[c];
    const right = T != null && x ? pill(status(share(x, "eng"), T, .05)) : `<span class="sub">${x ? x.n + " members" : ""}</span>`;
    return `<article class="card class-panel">
      <div class="card-head"><h3>${esc(c)} members</h3>${right}</div>
      ${x ? bandBlocks(x, xp) + compBar(x) : `<p class="empty">No report this week.</p>`}
      <div class="chart spark" data-class="${esc(c)}"></div>
      ${x ? `<dl class="facts"><dt>Within Engaged</dt><dd>Highly Engaged <b>${x.a[0]}</b> · Engaged <b>${x.a[1]}</b></dd></dl><dl class="facts"><dt>Within Risk</dt><dd>Moderate <b>${x.a[3]}</b> · High <b>${x.a[4]}</b></dd></dl>` : ""}
    </article>`;
  }).join("");
  box.querySelectorAll(".spark").forEach(sp => {
    const c = sp.dataset.class;
    shareCols(sp, { height: 48, get: x => eng(x, c), aria: `${c} members by engagement band, by week` });
  });
}
