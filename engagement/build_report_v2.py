"""Build GBCA_Member_Engagement_Report_New.html from scoring model v2.

  python build_report_v2.py --scores data/<date>/scores_v2.json --as-of "Oct 2, 2026" \
      --old-scores data/<date>/scores.json \
      [--compare <last week's scores_v2.json> --compare-label "Sep 26"] --out reports/GBCA_Member_Engagement_Report_New.html

The old report (build_report.py) is unchanged; this one shows the same members under model v2,
with the validation that supports it and a side-by-side count against the 2026 scorecard."""

import argparse
import html
import json
import os
import re

import model_v2 as mv

HERE = os.path.dirname(os.path.abspath(__file__))
TYPES = ("Active", "Associate", "Affiliate")
BAND_ORDER = ["Secure", "Stable", "Watch", "At Risk"]
BAND_KEY = {"Secure": "se", "Stable": "st", "Watch": "wa", "At Risk": "ar"}
WATCH = ("Watch", "At Risk")


def esc(s):
    return html.escape(str(s))


def norm(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").lower().replace("&", "and"))


def pct(n, d, places=0):
    return f"{100 * n / d:.{places}f}%" if d else "0%"


def money_k(v):
    return f"${v / 1000:,.0f}K" if v >= 1000 else f"${v:,.0f}"


SHORT = {("tenure", "first two years"): "new member (first two years)", ("tenure", "2-4 years"): "only 2-4 years in",
         ("spend", "under $1K"): "under $1K non-dues spend", ("spend", "$1K-5K"): "modest non-dues spend",
         ("recency", "6-12 months ago"): "activity stopped 6-12 months ago", ("recency", "none in 12 months"): "no activity in 12 months",
         ("dues", "paid 1-4 months late"): "dues paid late", ("dues", "4+ months late or unpaid"): "dues 4+ months late or unpaid",
         ("dues", "paid late or unpaid"): "dues paid late or unpaid", ("tier", "under $2M"): "firm under $2M",
         ("tier", "under $10M"): "firm under $10M", ("bargaining", "no"): "no bargaining rights",
         ("tenure", "5-9 years"): "5-9 years in", ("dues", "no dues invoice on record"): "no dues invoice on record"}


def why(member, model):
    """The two inputs that cost this member the most points, in plain words."""
    card = model["scorecards"][member["type"]]["groups"]
    lost = []
    for group, label in member["inputs"].items():
        if label is None:
            continue
        bins = card[group]
        pts = next(b["points"] for b in bins if b["label"] == label)
        gap = max(b["points"] for b in bins) - pts
        if gap >= 4:
            lost.append((gap, SHORT.get((group, label), f"{group}: {label}")))
    return "; ".join(t for _, t in sorted(lost, reverse=True)[:2]) or "-"


def build(scores, model, as_of, old, validation, compare=None, compare_label=""):
    members = scores["members"]
    total = len(members)
    by_type = {t: [m for m in members if m["type"] == t] for t in TYPES}
    watch = sorted([m for m in members if m["band"] in WATCH], key=lambda m: -m["risk"])
    at_risk = [m for m in members if m["band"] == "At Risk"]
    expected = sum(m["risk"] for m in members)
    dues_at_risk = sum(m["risk"] * m["dues"] for m in members)
    secure = [m for m in members if m["band"] == "Secure"]
    exp_t = {t: sum(m["risk"] for m in by_type[t]) for t in TYPES}
    w_t = {t: sum(m["band"] in WATCH for m in by_type[t]) for t in TYPES}
    seg = validation["segments"]
    aff, con = seg["Affiliate"], seg["contractors"]

    # old vs new on today's members
    old_level = {}
    if old:
        for t, d in old["types"].items():
            for m in d["members"]:
                old_level[norm(m["name"])] = m["corrected_level"]
    old_risk = [m for m in members if old_level.get(norm(m["name"])) in ("Moderate Risk", "High Risk")]
    old_risk_calm = [m for m in old_risk if m["band"] in ("Secure", "Stable")]
    new_only = [m for m in watch if old_level.get(norm(m["name"])) not in ("Moderate Risk", "High Risk")]

    # week over week
    moved_in, moved_out = [], []
    if compare:
        before = {norm(m["name"]): m["band"] for m in compare["members"]}
        moved_in = sorted([m for m in watch if before.get(norm(m["name"])) not in (None,) + WATCH], key=lambda m: -m["risk"])
        moved_out = [m for m in members if m["band"] not in WATCH and before.get(norm(m["name"])) in WATCH]

    dist = {t: {b: sum(m["band"] == b for m in by_type[t]) for b in BAND_ORDER} for t in TYPES}
    dist["All members"] = {b: sum(m["band"] == b for m in members) for b in BAND_ORDER}

    def counts_rows():
        out = []
        for b in reversed(BAND_ORDER):
            cells = "".join(f'<td class="n">{dist[t][b]}</td>' for t in TYPES + ("All members",))
            out.append(f'<tr><td><i class="sw b-{BAND_KEY[b]}"></i>{b}</td>{cells}</tr>')
        out.append('<tr><td><b>Expected to leave</b></td>' + "".join(f'<td class="n"><b>{exp_t[t]:.1f}</b></td>' for t in TYPES)
                   + f'<td class="n"><b>{expected:.1f}</b></td></tr>')
        return "".join(out)

    def row(m, extra=False):
        tr = '<tr class="pmore">' if extra else "<tr>"
        return (f'{tr}<td>{esc(m["name"])}</td><td>{m["type"]}</td><td class="n">{m["score"]}</td>'
                f'<td class="n {"up" if m["band"] == "At Risk" else ""}">{100 * m["risk"]:.0f}%</td><td class="why">{esc(why(m, model))}</td></tr>')
    top_aff = [m for m in watch if m["type"] == "Affiliate"][:9]
    top_con = [m for m in watch if m["type"] != "Affiliate"][:6]
    watch_rows = (f'<tr class="grp"><td colspan="5">Affiliates ({w_t["Affiliate"]} on the watch list; top {len(top_aff)})</td></tr>'
                  + "".join(row(m, i >= 7) for i, m in enumerate(top_aff))
                  + f'<tr class="grp"><td colspan="5">Active and Associate ({w_t["Active"] + w_t["Associate"]} on the watch list; top {len(top_con)})</td></tr>'
                  + "".join(row(m, i >= 4) for i, m in enumerate(top_con)))
    full_rows = "".join(
        f'<tr><td>{esc(m["name"])}</td><td>{m["type"]}</td><td>{m["band"]}</td><td class="n">{m["score"]}</td>'
        f'<td class="n">{100 * m["risk"]:.0f}%</td><td class="why">{esc(why(m, model))}</td></tr>' for m in watch)

    def card_table(t):
        card = model["scorecards"][t]
        th = mv.band_thresholds(model, t)
        rows = "".join(
            f'<tr><td>{esc(mv.GROUP_LABELS[g].split(",")[0])}</td><td>'
            + " &middot; ".join(f'{esc(b["label"])} <b>{b["points"]:.0f}</b>' for b in sorted(bins, key=lambda b: -b["points"]))
            + "</td></tr>" for g, bins in card["groups"].items())
        return (f'<div class="sc"><h3>{t}</h3><table class="sct">{rows}</table>'
                f'<p class="cut">At Risk at {th["At Risk"]:.0f} or below &middot; Watch {th["At Risk"]:.0f}&ndash;{th["Watch"]:.0f} &middot; '
                f'Secure above {th["Stable"]:.0f}</p></div>')

    def calib(seg_v):
        return " &middot; ".join(
            f'{c["band"]} {100 * c["left"] / c["member_years"]:.1f}% (model {100 * c["predicted"]:.1f}%)'
            for c in seg_v["calibration"] if c["member_years"] >= 20)

    of_a, nf_a = aff["old_flagged"], aff["new_flagged"]
    of_c, nf_c = con["old_flagged"], con["new_flagged"]
    hist_aff = validation["history"]["Affiliate"]
    last_year = max(hist_aff, key=int)
    aff_last = hist_aff[last_year]

    data = {"bands": BAND_ORDER, "keys": [BAND_KEY[b] for b in BAND_ORDER], "dist": dist}
    since = f" since {esc(compare_label)}" if compare else ""
    change_html = ""
    if compare:
        change_html = (f'<li><b>{len(moved_in)} members moved onto the watch list{since}</b> and {len(moved_out)} moved off.'
                       + (f' <span class="impact">New: {esc(", ".join(m["name"] for m in moved_in[:6]))}{" and more" if len(moved_in) > 6 else ""}.</span>' if moved_in else "")
                       + "</li>")

    css = open(os.path.join(HERE, "report_style.css"), encoding="utf-8").read()
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GBCA Engagement Report (New)</title>
<style>
{css}
  :root {{ --b-se: #1F4E79; --b-st: #6F9CC8; --b-wa: #E6737F; --b-ar: #CE0E2D; }}
  @media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --b-se: #3D72BA; --b-st: #A6C6EC; --b-wa: #F29AA4; --b-ar: #EE3B55; }} }}
  :root[data-theme="dark"] {{ --b-se: #3D72BA; --b-st: #A6C6EC; --b-wa: #F29AA4; --b-ar: #EE3B55; }}
  .b-se {{ background: var(--b-se); color: #FFFFFF; }} .b-st {{ background: var(--b-st); color: #2D2D2D; }}
  .b-wa {{ background: var(--b-wa); color: #2D2D2D; }} .b-ar {{ background: var(--b-ar); color: #FFFFFF; }}
  i.sw {{ display: inline-block; width: 9px; height: 9px; border-radius: 2px; margin-right: 6px; vertical-align: 0; }}
  .hdr-tags {{ display: flex; gap: 6px; align-items: center; flex-wrap: wrap; justify-content: flex-end; }}
  .grid > div {{ min-width: 0; }}
  tr.grp td {{ background: var(--panel); color: var(--ink); font-weight: 700; font-size: 11.5px; }}
  .chip {{ white-space: nowrap; font: 700 10.5px/1 var(--sans); letter-spacing: .08em; text-transform: uppercase; color: var(--surface); background: var(--ink); padding: 6px 8px; border-radius: 3px; margin-right: 6px; }}
  td.why {{ font-size: 11.5px; color: var(--muted); }}
  .scs {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }}
  .sc h3 {{ font: 700 13px/1.2 var(--serif); color: var(--red); margin: 0 0 4px; }}
  .sc:nth-child(2) h3 {{ color: var(--ink); }}
  table.sct td {{ font-size: 11px; padding: 2px 4px; vertical-align: top; }}
  table.sct td:first-child {{ white-space: nowrap; color: var(--ink); font-weight: 700; }}
  .cut {{ font-size: 11px; color: var(--muted); margin: 4px 0 0; }}
  details {{ margin-top: 6px; font-size: 12px; }}
  details summary {{ cursor: pointer; color: var(--red); font-weight: 700; }}
  .val td.n b {{ color: var(--ink); }}
  @media (max-width: 760px) {{ .scs {{ grid-template-columns: 1fr; }} }}
  @media print {{
    :root {{ --b-se: #1F4E79; --b-st: #6F9CC8; --b-wa: #E6737F; --b-ar: #CE0E2D; }}
    details, tr.pmore {{ display: none; }}
    section.cards {{ break-before: page; }}
    .grid {{ grid-template-columns: 1fr 1fr; grid-template-areas: none; }}
    .grid > div {{ display: block; }}
  }}
</style>
</head>
<body>
<div class="sheet">
  <header>
    <div>
      <p class="org">General Building Contractors Association</p>
      <h1>Member Engagement Report <span style="color:var(--red)">(New Model)</span></h1>
      <div class="meta">Live GrowthZone data as of {esc(as_of)} &middot; Scoring model v2, trained on ten years of renewals ({esc(model["training_cohorts"])}) &middot; Separate scorecards for Active, Associate and Affiliate</div>
    </div>
    <div class="hdr-tags"><span class="chip">Model v2</span><span class="tag">Internal &middot; Staff use only</span></div>
  </header>

  <div class="bluf"><b>Bottom line:</b> <b>{len(watch)} members ({pct(len(watch), total)})</b> are on the watch list: {w_t['Affiliate']} Affiliates, {w_t['Associate']} Associates and {w_t['Active']} Active. The model expects about <b>{expected:.0f} departures in the next 12 months</b> ({exp_t['Affiliate']:.0f} of them Affiliates), roughly {money_k(dues_at_risk)} in dues. The 2026 scorecard flags {len(old_risk)} members as at risk; on years it never saw, this model ranked members slightly more accurately and flagged far fewer, with bands that match actual departure rates.</div>

  <div class="kpis">
    <div class="kpi"><div class="label">Expected departures</div><div class="value alert">{expected:.0f}</div><div class="note">next 12 months &middot; Affiliate {exp_t['Affiliate']:.1f} &middot; Associate {exp_t['Associate']:.1f} &middot; Active {exp_t['Active']:.1f}</div></div>
    <div class="kpi"><div class="label">Watch list</div><div class="value alert">{len(watch)}</div><div class="note">At Risk {len(at_risk)} &middot; Watch {len(watch) - len(at_risk)} &middot; vs {len(old_risk)} under the 2026 scorecard</div></div>
    <div class="kpi"><div class="label">Dues at risk</div><div class="value">{money_k(dues_at_risk)}</div><div class="note">expected dues lost to departures, next 12 months</div></div>
    <div class="kpi"><div class="label">Secure</div><div class="value">{len(secure)}</div><div class="note">{pct(len(secure), total)} of members, under 3% chance of leaving</div></div>
    <div class="kpi"><div class="label">Accuracy vs old</div><div class="value">{aff['auc_new_out_of_time']:.2f}</div><div class="note">Affiliates, vs {aff['auc_old_out_of_time']:.2f}; contractors {con['auc_new_out_of_time']:.2f} vs {con['auc_old_out_of_time']:.2f} (test years 2023&ndash;25)</div></div>
  </div>

  <div class="grid">
    <div>
      <section>
        <h2><span class="num">1</span>Risk bands by member type</h2>
        <div class="legend" aria-hidden="true">{"".join(f'<span><i class="b-{BAND_KEY[b]}"></i>{b}</span>' for b in BAND_ORDER)}</div>
        <div class="bars" id="bars" role="img" aria-label="Stacked bars of risk band share by member type; counts are in the table below."></div>
        <div class="tablewrap dist">
          <table aria-label="Risk band counts">
            <thead><tr><th>Band <span style="font-weight:400">(chance of leaving in 12 months)</span></th>{"".join(f'<th class="n">{t}</th>' for t in TYPES)}<th class="n">All</th></tr></thead>
            <tbody>{counts_rows()}</tbody>
          </table>
        </div>
        <p class="cut">Bands: At Risk 15%+ &middot; Watch 7&ndash;15% &middot; Stable 3&ndash;7% &middot; Secure under 3%. Same meaning for every member type.</p>
      </section>

      <section>
        <h2><span class="num">2</span>Highest risk right now</h2>
        <div class="tablewrap"><table>
          <thead><tr><th>Member</th><th>Type</th><th class="n">Score</th><th class="n">Risk</th><th>Why</th></tr></thead>
          <tbody>{watch_rows}</tbody>
        </table></div>
        <details><summary>All {len(watch)} watch-list members</summary>
          <div class="tablewrap"><table><thead><tr><th>Member</th><th>Type</th><th>Band</th><th class="n">Score</th><th class="n">Risk</th><th>Why</th></tr></thead><tbody>{full_rows}</tbody></table></div>
        </details>
      </section>
    </div>

    <div>
      <section>
        <h2><span class="num">3</span>What the model found</h2>
        <ol class="findings">
          {change_html}
          <li><b>Affiliates carry most of the risk.</b> {w_t['Affiliate']} of {len(by_type['Affiliate'])} are on the watch list. Affiliate departures ran {pct(aff_last[0], aff_last[1], 1)} in the year to Sep {int(last_year) + 1}, above the model's ten-year calibration, so treat Affiliate risk as a floor. <span class="impact">Tenure is the strongest Affiliate signal; the first two years are the danger zone.</span></li>
          <li><b>Late dues are an early warning.</b> Affiliates whose dues were 4+ months late or unpaid on the scoring date left far more often; for contractors, any late payment lowers the score. <span class="impact">Billing sees this before anyone else does.</span></li>
          <li><b>Lapsed activity matters more than none.</b> Members whose last event or purchase was 6&ndash;12 months ago score lowest on recency, below members who never attend. <span class="impact">A recent drop-off is a change in behavior worth a call.</span></li>
          <li><b>{len(old_risk_calm)} members the 2026 scorecard calls at risk are Secure or Stable here</b>, and {len(new_only)} {"member" if len(new_only) == 1 else "members"} on this watch list {"was" if len(new_only) == 1 else "were"} not flagged before. <span class="impact">Size, dues payment and recent activity now count; committee seats do not (see method).</span></li>
        </ol>
      </section>

      <section class="val">
        <h2><span class="num">4</span>Validation against the 2026 scorecard</h2>
        <div class="tablewrap"><table>
          <thead><tr><th>Test</th><th class="n">2026 scorecard</th><th class="n">Model v2</th></tr></thead>
          <tbody>
            <tr><td>Affiliates: ranking accuracy, test years 2023&ndash;25</td><td class="n">{aff['auc_old_out_of_time']:.2f}</td><td class="n"><b>{aff['auc_new_out_of_time']:.2f}</b></td></tr>
            <tr><td>Affiliates: share flagged / flagged who left (2020&ndash;25)</td><td class="n">{pct(of_a[0], of_a[2])} / {pct(of_a[1], of_a[0], 1)}</td><td class="n"><b>{pct(nf_a[0], nf_a[2])} / {pct(nf_a[1], nf_a[0], 1)}</b></td></tr>
            <tr><td>Contractors: ranking accuracy, test years 2023&ndash;25</td><td class="n">{con['auc_old_out_of_time']:.2f}</td><td class="n"><b>{con['auc_new_out_of_time']:.2f}</b></td></tr>
            <tr><td>Contractors: share flagged / flagged who left (2020&ndash;25)</td><td class="n">{pct(of_c[0], of_c[2])} / {pct(of_c[1], of_c[0], 1)}</td><td class="n"><b>{pct(nf_c[0], nf_c[2])} / {pct(nf_c[1], nf_c[0], 1)}</b></td></tr>
          </tbody>
        </table></div>
        <p class="cut"><b>Do the bands mean what they say?</b> Actual departure rates on held-out years. Affiliates: {calib(aff)}. Contractors: {calib(con)}.</p>
      </section>
    </div>
  </div>

  <section class="cards">
    <h2><span class="num">5</span>The scorecards (points out of 100; higher is more engaged)</h2>
    <div class="scs">{card_table("Active")}{card_table("Associate")}{card_table("Affiliate")}</div>
  </section>

  <section class="wide">
    <h2><span class="num">6</span>Method and limits</h2>
    <div class="cols3">
      <p><b>Training.</b> Every member on Oct 1 of 2016&ndash;2025 was described with GrowthZone data dated on or before that day and labeled by whether it was still a member a year later ({aff['member_years'] + con['member_years']:,} member-years, {aff['left'] + con['left']} departures). Billing detail (events, payment dates) starts in 2019, so activity is learned from 2020 on; tenure and size use all ten years.</p>
      <p><b>Models.</b> Affiliates have their own model. Active and Associate share one with separate size tiers and an Active adjustment, because Active members had only {validation['segments']['contractors']['by_type']['Active']['left']} departures in the six full-data years. Accuracy is tested on years each model never saw. Ranking accuracy (0.5 = coin flip, 1.0 = perfect) is near the ceiling GrowthZone data allows; the larger gain is labels that match reality.</p>
      <p><b>Limits.</b> Committee seats are not scored: GrowthZone stores only current rosters, which credits members who joined committees after the scoring date and made the old committee effect look larger than it is. Bargaining rights and headcount are current values. Free event registrations are not in the API. Recalibrate each fall as a new year of outcomes arrives.</p>
    </div>
  </section>

  <footer>
    <span>Source: GrowthZone API, GBCA tenant, pulled {esc(as_of)}. Model v2 trained {esc(model["trained"])}. The original report (GBCA_Member_Engagement_Report.html) is unchanged.</span>
    <span>Generated by engagement/build_report_v2.py</span>
  </footer>
</div>
<div class="tip" id="tip" role="tooltip"></div>
<script>
  const D = {json.dumps(data)};
  const bars = document.getElementById("bars");
  const pct = (n, d) => (100 * n / d).toFixed(1) + "%";
  for (const [who, counts] of Object.entries(D.dist)) {{
    const n = D.bands.reduce((a, b) => a + counts[b], 0), watch = counts["Watch"] + counts["At Risk"];
    const label = document.createElement("div"); label.className = "who"; label.innerHTML = `${{who}}<small>n = ${{n}}</small>`;
    const bar = document.createElement("div"); bar.className = "bar";
    D.bands.forEach((b, i) => {{
      if (!counts[b]) return;
      const seg = document.createElement("div"); seg.className = "seg b-" + D.keys[i]; seg.style.flex = counts[b]; seg.tabIndex = 0;
      seg.dataset.tip = `${{who}} · ${{b}}: ${{counts[b]}} (${{pct(counts[b], n)}})`;
      if (counts[b] / n >= 0.08) seg.textContent = counts[b];
      bar.appendChild(seg);
    }});
    const risk = document.createElement("div"); risk.className = "risk"; risk.innerHTML = `<b>${{pct(watch, n)}}</b>watch list`;
    bars.append(label, bar, risk);
  }}
  const tip = document.getElementById("tip");
  const show = (el, x, y) => {{ tip.textContent = el.dataset.tip; tip.style.left = (x + 12) + "px"; tip.style.top = (y - 30) + "px"; tip.style.opacity = 1; }};
  const hide = () => {{ tip.style.opacity = 0; }};
  bars.addEventListener("mousemove", e => {{ const s = e.target.closest(".seg"); s ? show(s, e.clientX, e.clientY) : hide(); }});
  bars.addEventListener("mouseleave", hide);
  bars.addEventListener("focusin", e => {{ const s = e.target.closest(".seg"); if (s) {{ const r = s.getBoundingClientRect(); show(s, r.left, r.top); }} }});
  bars.addEventListener("focusout", hide);
</script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description="Build the model v2 engagement report.")
    parser.add_argument("--scores", required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--old-scores", help="score_engagement.py JSON for the same pull (2026 scorecard)")
    parser.add_argument("--validation", default=os.path.join(HERE, "model_validation_v2.json"))
    parser.add_argument("--compare", help="last week's scores_v2 JSON")
    parser.add_argument("--compare-label", default="")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    load = lambda p: json.load(open(p, encoding="utf-8")) if p and os.path.exists(p) else None
    page = build(load(args.scores), mv.load_model(), args.as_of, load(args.old_scores), load(args.validation),
                 load(args.compare), args.compare_label)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
