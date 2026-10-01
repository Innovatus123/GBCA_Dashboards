const total = o => Object.values(o).reduce((a, b) => a + b, 0);
  const pct = (n, d) => (100 * n / d).toFixed(1) + "%";

  const bars = document.getElementById("bars");
  for (const [who, counts] of Object.entries(VALIDATED)) {
    const n = total(counts), atRisk = counts.mo + counts.hi;
    const label = document.createElement("div");
    label.className = "who";
    label.innerHTML = `${who}<small>n = ${n}</small>`;
    const bar = document.createElement("div");
    bar.className = "bar";
    for (const [key, name] of LEVELS) {
      if (!counts[key]) continue;
      const seg = document.createElement("div");
      seg.className = "seg " + key;
      seg.style.flex = counts[key];
      seg.tabIndex = 0;
      seg.dataset.tip = `${who} · ${name}: ${counts[key]} (${pct(counts[key], n)}) · ${COMPARE_LABEL} ${PUBLISHED[who][key]}`;
      if (counts[key] / n >= 0.08) seg.textContent = counts[key];
      bar.appendChild(seg);
    }
    const risk = document.createElement("div");
    risk.className = "risk";
    risk.innerHTML = `<b>${pct(atRisk, n)}</b>at risk`;
    bars.append(label, bar, risk);
  }

  const rows = document.getElementById("counts");
  for (const [key, name] of LEVELS) {
    const cells = Object.keys(VALIDATED).map(who => {
      const p = PUBLISHED[who][key], v = VALIDATED[who][key];
      return `<td class="n"><span class="was">${p}</span> &rarr; <span class="${v !== p ? "up" : ""}">${v}</span></td>`;
    }).join("");
    rows.insertAdjacentHTML("beforeend", `<tr><td>${name}</td>${cells}</tr>`);
  }
  const totals = Object.keys(VALIDATED).map(who => `<td class="n"><b><span class="was">${total(PUBLISHED[who])}</span> &rarr; ${total(VALIDATED[who])}</b></td>`).join("");
  rows.insertAdjacentHTML("beforeend", `<tr><td><b>Total members</b></td>${totals}</tr>`);

  const moves = document.getElementById("moves");
  for (const [name, was, now, why] of MOVES) {
    moves.insertAdjacentHTML("beforeend", `<tr><td>${name}</td><td class="n was">${was}</td><td class="n up">${now}</td><td class="why">${why}</td></tr>`);
  }

  const tip = document.getElementById("tip");
  const show = (el, x, y) => { tip.textContent = el.dataset.tip; tip.style.left = (x + 12) + "px"; tip.style.top = (y - 30) + "px"; tip.style.opacity = 1; };
  const hide = () => { tip.style.opacity = 0; };
  bars.addEventListener("mousemove", e => { const s = e.target.closest(".seg"); s ? show(s, e.clientX, e.clientY) : hide(); });
  bars.addEventListener("mouseleave", hide);
  bars.addEventListener("focusin", e => { const s = e.target.closest(".seg"); if (s) { const r = s.getBoundingClientRect(); show(s, r.left, r.top); } });
  bars.addEventListener("focusout", hide);
