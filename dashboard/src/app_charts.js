/* GBCA Dashboard, part 2 of 4: charts and tables. */

/* Line / sparkline. One function so both share the selected-week and hover behaviour. */
function trendChart(box, o) {
  box.replaceChildren();
  const W = Math.max(160, box.clientWidth), H = o.height, axes = !!o.axes;
  const m = axes ? { t: 24, r: 16, b: 26, l: 36 } : { t: 8, r: 6, b: 6, l: 6 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b, v = o.values;
  const all = o.target != null ? v.concat(o.target) : v;
  let lo = Math.min(...all), hi = Math.max(...all);
  const step = o.step || niceStep(hi - lo);
  lo = Math.floor((lo - step * .25) / step) * step; hi = Math.ceil((hi + step * .25) / step) * step;
  if (o.min != null) lo = Math.max(lo, o.min);
  if (o.max != null) hi = Math.min(hi, o.max);
  const x = i => m.l + i * iw / (N - 1), y = val => m.t + ih - (val - lo) / (hi - lo) * ih;
  const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": o.aria }, box);
  const half = iw / (N - 1) / 2, sx = x(state.sel);
  if (axes) el("rect", { class: "sel-band", x: Math.max(m.l, sx - half), y: m.t, width: Math.min(m.l + iw, sx + half) - Math.max(m.l, sx - half), height: ih }, svg);
  if (axes) {
    for (let t = lo; t <= hi + 1e-9; t += step) {
      el("line", { class: t === lo ? "baseline" : "gridline", x1: m.l, x2: m.l + iw, y1: Math.round(y(t)) + .5, y2: Math.round(y(t)) + .5 }, svg);
      el("text", { class: "tick", x: m.l - 8, y: y(t) + 4, "text-anchor": "end" }, svg).textContent = o.tick(t);
    }
    const every = iw / N < 34 ? 3 : iw / N < 52 ? 2 : 1;
    for (let i = 0; i < N; i++) {
      if (i !== state.sel && (N - 1 - i) % every) continue;
      el("text", { class: "tick" + (i === state.sel ? " sel" : ""), x: x(i), y: H - 6, "text-anchor": i === 0 ? "start" : i === N - 1 ? "end" : "middle" }, svg).textContent = wk(i);
    }
  }
  if (o.target != null) {
    el("line", { class: "target", x1: m.l, x2: m.l + iw, y1: Math.round(y(o.target)) + .5, y2: Math.round(y(o.target)) + .5 }, svg);
    if (axes) el("text", { class: "target-label", x: m.l + 4, y: y(o.target) - 6 }, svg).textContent = o.targetLabel;
  }
  const pts = v.map((val, i) => [x(i), y(val)]);
  if (axes) el("path", { class: "area", d: `M${pts[0][0]},${y(lo)}L${pts.map(p => p.join(",")).join("L")}L${pts[N - 1][0]},${y(lo)}Z` }, svg);
  el("path", { class: "line" + (axes ? "" : " spark-line"), d: "M" + pts.map(p => p.join(",")).join("L") }, svg);
  const xh = el("line", { class: "xhair", y1: m.t, y2: m.t + ih, visibility: "hidden" }, svg);
  const hov = el("circle", { class: "dot-hover", r: 4, visibility: "hidden" }, svg);
  el("circle", { class: "dot-sel", cx: pts[state.sel][0], cy: pts[state.sel][1], r: axes ? 5 : 4 }, svg);
  if (axes) {
    const lx = pts[state.sel][0], anchor = state.sel === 0 ? "start" : state.sel === N - 1 ? "end" : "middle";
    const above = pts[state.sel][1] - m.t > 22;
    el("text", { class: "val-label", x: lx, y: above ? pts[state.sel][1] - 11 : pts[state.sel][1] + 21, "text-anchor": anchor }, svg).textContent = o.fmt(v[state.sel]);
  }
  const hit = el("rect", { class: "hit", x: m.l - half, y: 0, width: iw + 2 * half, height: H }, svg);
  const nearest = e => { const r = svg.getBoundingClientRect(); return Math.max(0, Math.min(N - 1, Math.round((e.clientX - r.left - m.l) / (iw / (N - 1))))); };
  hit.addEventListener("pointermove", e => {
    const i = nearest(e);
    xh.setAttribute("x1", pts[i][0]); xh.setAttribute("x2", pts[i][0]); xh.setAttribute("visibility", axes ? "visible" : "hidden");
    hov.setAttribute("cx", pts[i][0]); hov.setAttribute("cy", pts[i][1]); hov.setAttribute("visibility", i === state.sel ? "hidden" : "visible");
    showTip(e, wkTitle(i), o.tipRows(i));
  });
  hit.addEventListener("pointerleave", () => { xh.setAttribute("visibility", "hidden"); hov.setAttribute("visibility", "hidden"); hideTip(); });
  hit.addEventListener("click", e => select(nearest(e)));
}

/* Grouped columns: opened (context grey) beside resolved (ink). Labels, selection and tooltips are passed in,
   so the same chart serves any period grain. */
function columnChart(box, o) {
  box.replaceChildren();
  const n = o.labels.length;
  const W = Math.max(200, box.clientWidth), H = o.height, m = { t: 12, r: 6, b: 26, l: 30 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const max = Math.max(1, ...o.series.flatMap(s => s.values)), step = niceStep(max), hi = Math.ceil(max / step) * step;
  const y = v => m.t + ih - v / hi * ih, band = iw / n, ns = o.series.length;
  const bw = Math.max(3, Math.min(14, (band * .72 - 2 * (ns - 1)) / ns)), gw = ns * bw + 2 * (ns - 1);
  const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": o.aria }, box);
  if (o.sel != null) el("rect", { class: "sel-band", x: m.l + o.sel * band, y: m.t, width: band, height: ih }, svg);
  for (let t = 0; t <= hi + 1e-9; t += step) {
    el("line", { class: t === 0 ? "baseline" : "gridline", x1: m.l, x2: m.l + iw, y1: Math.round(y(t)) + .5, y2: Math.round(y(t)) + .5 }, svg);
    el("text", { class: "tick", x: m.l - 8, y: y(t) + 4, "text-anchor": "end" }, svg).textContent = t;
  }
  const every = band < 30 ? 3 : band < 44 ? 2 : 1;
  for (let i = 0; i < n; i++) {
    const gx = m.l + i * band + (band - gw) / 2;
    o.series.forEach((s, k) => {
      el("path", { class: s.cls, d: barPath(gx + k * (bw + 2), Math.round(y(0)), bw, Math.round(y(0)) - y(s.values[i])) }, svg);
    });
    if (i === o.sel || !((n - 1 - i) % every))
      el("text", { class: "tick" + (i === o.sel ? " sel" : ""), x: m.l + i * band + band / 2, y: H - 6, "text-anchor": "middle" }, svg).textContent = o.labels[i];
    const hit = el("rect", { class: "hit", x: m.l + i * band, y: 0, width: band, height: H }, svg);
    if (!o.onPick) hit.style.cursor = "default";
    hit.addEventListener("pointermove", e => showTip(e, o.tipTitle(i), o.tipRows(i)));
    hit.addEventListener("pointerleave", hideTip);
    if (o.onPick) hit.addEventListener("click", () => o.onPick(i));
  }
}

/* Horizontal bars in HTML so labels wrap naturally at any width. */
function hbars(box, rows, o) {
  box.replaceChildren();
  const max = o.max || Math.max(...rows.map(r => r.value));
  for (const r of rows) {
    const row = document.createElement("div"); row.className = "hb-row";
    row.innerHTML = `<div class="hb-label">${esc(r.label)}</div><div class="hb-track"><div class="hb-bar" style="width:calc((100% - 76px) * ${r.value / max})"></div><span class="hb-val">${esc(o.fmt(r.value))}</span>${o.ref != null ? `<span class="hb-ref" style="left:calc((100% - 76px) * ${o.ref / max})"></span>` : ""}</div>`;
    row.addEventListener("pointermove", e => showTip(e, r.label, r.tip || [{ value: o.fmt(r.value) }]));
    row.addEventListener("pointerleave", hideTip);
    box.appendChild(row);
  }
}
function table(headers, rows, foot) {
  const th = headers.map(h => `<th${h.num ? ' class="num"' : ""}>${esc(h.label)}</th>`).join("");
  const tr = r => `<tr>${r.map((c, k) => `<td${headers[k].num ? ' class="num"' : ""}>${c}</td>`).join("")}</tr>`;
  return `<thead><tr>${th}</tr></thead><tbody>${rows.map(tr).join("")}</tbody>${foot ? `<tfoot>${tr(foot)}</tfoot>` : ""}`;
}
const setTable = (id, headers, rows, foot) => { $(id).innerHTML = `<table>${table(headers, rows, foot)}</table>`; };
const setTableInto = (id, headers, rows, foot) => { $(id).innerHTML = table(headers, rows, foot); };

/* 100% stacked columns, one per week: Engaged on top, Low Risk, then Risk on the baseline so its share reads
   directly. A week without a live report keeps an empty slot, so the calendar lines up with every other chart. */
function shareCols(box, o) {
  box.replaceChildren();
  const W = Math.max(160, box.clientWidth), H = o.height, axes = !!o.axes;
  const m = axes ? { t: 4, b: 22 } : { t: 2, b: 2 }, ih = H - m.t - m.b, band = W / N;
  const bw = Math.max(4, Math.min(26, band * .62));
  const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": o.aria }, box);
  el("rect", { class: "sel-band", x: state.sel * band, y: 0, width: band, height: m.t + ih + 2 }, svg);
  const every = band < 34 ? 3 : band < 52 ? 2 : 1;
  for (let i = 0; i < N; i++) {
    const e = o.get(i), x = i * band + (band - bw) / 2;
    if (!e || !e.n) el("rect", { class: "col-none", x, y: m.t + ih - 2, width: bw, height: 2 }, svg);
    else {
      let y = m.t;
      BANDS.forEach(([k, , c], j) => {
        const h = e[k] / e.n * ih, gap = j < 2 && h > 1.5 ? 1 : 0;
        if (h > 0) el("rect", { class: "col-" + c, x, y, width: bw, height: h - gap }, svg);
        y += h;
      });
    }
    if (axes && (i === state.sel || !((N - 1 - i) % every)))
      el("text", { class: "tick" + (i === state.sel ? " sel" : ""), x: i * band + band / 2, y: H - 6, "text-anchor": "middle" }, svg).textContent = wk(i);
    const hit = el("rect", { class: "hit", x: i * band, y: 0, width: band, height: H }, svg);
    hit.addEventListener("pointermove", ev => showTip(ev, wkTitle(i), e && e.n
      ? [{ key: "tk-e", value: pct(share(e, "eng")), label: `Engaged (${e.eng})` }, { key: "tk-a", value: pct(share(e, "low")), label: `Low Risk (${e.low})` },
         { key: "tk-r", value: pct(share(e, "risk")), label: `Risk (${e.risk})` }, { value: String(e.n), label: "members" }]
      : [{ value: "No live report", label: "this week" }]));
    hit.addEventListener("pointerleave", hideTip);
    hit.addEventListener("click", () => select(i));
  }
}
