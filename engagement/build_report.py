"""Build the one-page GBCA Member Engagement Report from scored GrowthZone data.

Usage:
  python build_report.py --scores data/<date>/scores.json --compare data/recon/scores.json \
      --as-of "Oct 1, 2026" --window "Oct 1, 2025 - Sep 30, 2026" --compare-label "Aug 4" \
      --out reports/GBCA_Member_Engagement_Report_<date>.html

--scores is the score_engagement.py JSON for the period being reported. --compare is
an earlier period scored the same way; the report shows what changed between them.
"""

import argparse
import html
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
LEVELS = [("he", "Highly Engaged"), ("en", "Engaged"), ("lo", "Low Risk"), ("mo", "Moderate Risk"), ("hi", "High Risk")]
TYPES = ("Active", "Associate", "Affiliate")
ENGAGED_FLOOR = {"Active": 75, "Associate": 75, "Affiliate": 65}
RISK = ("Moderate Risk", "High Risk")
SHORT = {"Highly Engaged": "HiEng", "Engaged": "Eng", "Low Risk": "Low", "Moderate Risk": "Mod", "High Risk": "High"}


def norm(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").lower().replace("&", "and"))


def members(scores):
    return [dict(m, type=t) for t, d in scores["types"].items() for m in d["members"]]


def distribution(rows):
    out = {}
    for t in TYPES + ("All members",):
        sub = [m for m in rows if t == "All members" or m["type"] == t]
        out[t] = {key: sum(m["corrected_level"] == name for m in sub) for key, name in LEVELS}
    return out


def pct(n, d):
    return f"{100 * n / d:.1f}%" if d else "0.0%"


def esc(text):
    return html.escape(str(text))


def short_list(rows, n, fmt):
    return ", ".join(fmt(m) for m in rows[:n]) + (f", and {len(rows) - n} more" if len(rows) > n else "")


def mover_label(pair):
    before, after = pair
    return f"{after['name']} ({SHORT[before['corrected_level']]} to {SHORT[after['corrected_level']]})"


def build(scores, compare, as_of, window, compare_label):
    now = members(scores)
    before = members(compare) if compare else []
    dist, base = distribution(now), distribution(before) if before else None
    total = len(now)
    at_risk = [m for m in now if m["corrected_level"] in RISK]
    active = [m for m in now if m["type"] == "Active"]
    active_risk = sorted([m for m in active if m["corrected_level"] in RISK], key=lambda m: m["corrected_score"])
    engaged = [m for m in now if m["corrected_level"] in ("Engaged", "Highly Engaged")]
    first_year = [m for m in now if m["years"] <= 1]
    first_year_high = [m for m in first_year if m["corrected_level"] == "High Risk"]
    high = [m for m in now if m["corrected_level"] == "High Risk"]
    tenured_high = sorted([m for m in high if m["years"] >= 20], key=lambda m: -m["years"])
    near = sorted([m for m in now if m["corrected_level"] == "Low Risk"
                   and m["corrected_score"] > ENGAGED_FLOOR[m["type"]] - 5], key=lambda m: -m["corrected_score"])
    dues_rows = sum(1 for m in now if m["dues_populated"])

    # Change since the comparison period, matched by organization name.
    prior = {norm(m["name"]): m for m in before}
    current = {norm(m["name"]): m for m in now}
    order = [name for _, name in LEVELS]
    worse, better = [], []
    for k, m in current.items():
        p = prior.get(k)
        if p and p["corrected_level"] != m["corrected_level"]:
            (worse if order.index(m["corrected_level"]) > order.index(p["corrected_level"]) else better).append((p, m))
    newly_risk = sorted([(p, m) for p, m in worse if m["corrected_level"] in RISK and p["corrected_level"] not in RISK],
                        key=lambda pm: pm[1]["corrected_score"])
    joined = sorted([m for k, m in current.items() if k not in prior], key=lambda m: m["name"])
    left = sorted([m for k, m in prior.items() if k not in current], key=lambda m: m["name"])
    base_total = len(before)
    base_risk = sum(1 for m in before if m["corrected_level"] in RISK)

    risk_share = 100 * len(at_risk) / total if total else 0
    trend = ""
    if before:
        delta = risk_share - (100 * base_risk / base_total)
        trend = (f" That is {abs(delta):.1f} points {'higher' if delta > 0 else 'lower'} than {compare_label} "
                 f"({pct(base_risk, base_total)}, rescored the same way).")
    active_share = pct(len(active_risk), len(active))

    moves_rows = "".join(
        f"<tr><td>{esc(m['name'])}</td><td class=\"n\">{m['corrected_score']:.1f}</td>"
        f"<td class=\"n up\">{SHORT[m['corrected_level']]}</td><td class=\"n\">{int(m['years'])}</td>"
        f"<td class=\"n\">{int(m['events'])}</td><td class=\"n\">${m['non_spend']:,.0f}</td></tr>"
        for m in active_risk)

    change_items = []
    if before:
        moved_in = len([1 for p, m in better if p["corrected_level"] in RISK and m["corrected_level"] not in RISK])
        examples = short_list(newly_risk, 8, mover_label)
        change_items.append(
            f"<li><b>{len(newly_risk)} members moved into Moderate or High Risk</b> since {compare_label}, and "
            f"{moved_in} moved out. <span class=\"impact\">{esc(examples)}</span></li>")
        change_items.append(
            f"<li><b>{len(joined)} joined and {len(left)} left</b> since {compare_label} "
            f"({base_total} to {total} members). "
            f"<span class=\"impact\">Joined: {esc(short_list(joined, 6, lambda m: m['name']))}. "
            f"Left: {esc(short_list(left, 6, lambda m: m['name']))}.</span></li>")
        change_items.append(
            f"<li><b>{len(worse)} members slipped a band and {len(better)} improved</b> overall. "
            f"<span class=\"impact\">Same organizations, same scoring rules, a newer 12-month window.</span></li>")
    change_items.append(
        f"<li><b>Dues now come from GrowthZone billing.</b> {dues_rows} of {total} members have dues recorded in the "
        f"window, versus 27 of 340 in the Aug 4 export. <span class=\"impact\">The dues points in each scorecard can "
        f"now be awarded.</span></li>")

    data = {
        "VALIDATED": dist,
        "PUBLISHED": base or {t: {k: 0 for k, _ in LEVELS} for t in dist},
        "COMPARE_LABEL": compare_label if before else "prior",
    }
    counts_label = f"{esc(compare_label)} &rarr; {esc(as_of)}" if before else esc(as_of)

    def counts_rows():
        rows = []
        for key, name in LEVELS:
            cells = []
            for who in dist:
                v = dist[who][key]
                if base:
                    p = base[who][key]
                    cells.append(f"<td class=\"n\"><span class=\"was\">{p}</span> &rarr; <span class=\"{'up' if v != p else ''}\">{v}</span></td>")
                else:
                    cells.append(f"<td class=\"n\">{v}</td>")
            rows.append(f"<tr><td>{name}</td>{''.join(cells)}</tr>")
        tot = []
        for who in dist:
            n = sum(dist[who].values())
            tot.append(f"<td class=\"n\"><b>" + (f"<span class=\"was\">{sum(base[who].values())}</span> &rarr; " if base else "") + f"{n}</b></td>")
        rows.append(f"<tr><td><b>Total members</b></td>{''.join(tot)}</tr>")
        return "".join(rows)

    css = open(os.path.join(HERE, "report_style.css"), encoding="utf-8").read()
    script = open(os.path.join(HERE, "report_script.js"), encoding="utf-8").read()
    # Keep the bar chart and tooltip code; the tables are rendered here, server side.
    script = script[: script.index('const rows = document.getElementById("counts");')] + script[script.index("const tip = document.getElementById"):]

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GBCA Engagement Report</title>
<style>
{css}</style>
</head>
<body>
<div class="sheet">
  <header>
    <div>
      <p class="org">General Building Contractors Association</p>
      <h1>Member Engagement Report</h1>
      <div class="meta">Live GrowthZone data as of {esc(as_of)} &middot; Events and spend {esc(window)} &middot; Scored against the 2026 scorecards</div>
    </div>
    <div class="tag">Internal &middot; Staff use only</div>
  </header>

  <div class="bluf"><b>Bottom line:</b> {len(at_risk)} of {total} members ({risk_share:.0f}%) are Moderate or High Risk.{trend} Among Active members, <b>{active_share} are at risk</b> ({len(active_risk)} of {len(active)}). Associate and Affiliate members still carry most of the risk.</div>

  <div class="kpis">
    <div class="kpi"><div class="label">Current members</div><div class="value">{total}</div><div class="note">{' &middot; '.join(f'{t} {sum(dist[t].values())}' for t in TYPES)}</div></div>
    <div class="kpi"><div class="label">Moderate + High Risk</div><div class="value alert">{risk_share:.1f}%</div><div class="note">{len(at_risk)} members{f' &middot; {compare_label}: {pct(base_risk, base_total)}' if before else ''}</div></div>
    <div class="kpi"><div class="label">Active members at risk</div><div class="value alert">{active_share}</div><div class="note">{len(active_risk)} of {len(active)}</div></div>
    <div class="kpi"><div class="label">Engaged or better</div><div class="value">{len(engaged)}</div><div class="note">{pct(len(engaged), total)} of members</div></div>
    <div class="kpi"><div class="label">High Risk in first year</div><div class="value">{len(first_year_high)}</div><div class="note">{pct(len(first_year_high), len(high))} of all High Risk are &le;1-year members</div></div>
  </div>

  <div class="grid">
    <div>
      <section class="s-dist">
        <h2><span class="num">1</span>Engagement distribution</h2>
        <div class="legend" aria-hidden="true">
          <span><i class="he"></i>Highly Engaged</span><span><i class="en"></i>Engaged</span><span><i class="lo"></i>Low Risk</span><span><i class="mo"></i>Moderate Risk</span><span><i class="hi"></i>High Risk</span>
        </div>
        <div class="bars" id="bars" role="img" aria-label="Stacked bars of engagement level share by member type; values are in the table below."></div>
        <div class="tablewrap dist">
          <table aria-label="Engagement level counts">
            <thead><tr><th>Level <span style="font-weight:400">({counts_label})</span></th><th class="n">Active</th><th class="n">Associate</th><th class="n">Affiliate</th><th class="n">All members</th></tr></thead>
            <tbody id="counts">{counts_rows()}</tbody>
          </table>
        </div>
      </section>

      <section class="s-moves">
        <h2><span class="num">2</span>Active members at risk</h2>
        <div class="tablewrap">
          <table>
            <thead><tr><th>Member</th><th class="n">Score</th><th class="n">Level</th><th class="n">Years</th><th class="n">Event regs</th><th class="n">Non-dues</th></tr></thead>
            <tbody>{moves_rows}</tbody>
          </table>
        </div>
      </section>
    </div>

    <div>
      <section class="s-findings">
        <h2><span class="num">3</span>What changed{f' since {esc(compare_label)}' if before else ''}</h2>
        <ol class="findings">
          {''.join(change_items)}
        </ol>
      </section>

      <section class="s-focus">
        <h2><span class="num">4</span>Where to focus</h2>
        <div class="focus">
          <div class="card"><h3><span class="big">{len(active_risk)}</span>Active members at risk</h3><p>Highest dues and bargaining value. Outreach should come from executives and Board peers (see table 2).</p></div>
          <div class="card"><h3><span class="big">{len(first_year)}</span>First-year members</h3><p>{len(first_year_high)} score High Risk because the model rewards tenure and event history they can't have yet. Put them on a 90-day onboarding track.</p></div>
          <div class="card"><h3><span class="big">{len(tenured_high)}</span>High Risk with 20+ years</h3><p>Long-time renewers with little participation. A quarterly relationship call is enough.</p><p class="names">{esc(short_list(tenured_high, 6, lambda m: f"{m['name']} ({int(m['years'])} yrs)"))}</p></div>
          <div class="card"><h3><span class="big">{len(near)}</span>Within 5 points of Engaged</h3><p>One committee seat or 2&ndash;3 events moves them up a band.</p><p class="names">{esc(short_list(near, 11, lambda m: m['name']))}</p></div>
        </div>
      </section>
    </div>
  </div>

  <section class="wide">
    <h2><span class="num">5</span>Method</h2>
    <div class="cols3">
      <p><b>Source.</b> Pulled directly from GBCA's GrowthZone account through the API: memberships, organization custom fields and category lists, related contacts, and every purchase in the window (event registrations, dues and other spend).</p>
      <p><b>Scoring.</b> 2026 Active, Associate and Affiliate scorecards as written. Board points go only to Board members, blank fields score zero, and report footer lines are never counted. These fixes correct the errors found in the Aug 4 model.</p>
      <p><b>Definitions.</b> Event attendees are registrants, which is GrowthZone's own definition. Non-dues spend includes purchases by people at the company. The window is the trailing 12 months, the same window as the saved GrowthZone report.</p>
    </div>
  </section>

  <footer>
    <span>Source: GrowthZone API, GBCA tenant, pulled {esc(as_of)}. Comparison: Aug 4, 2026 GrowthZone export rescored with the corrected model.</span>
    <span>Generated by engagement/build_report.py</span>
  </footer>
</div>
<div class="tip" id="tip" role="tooltip"></div>

<script>
  const LEVELS = {json.dumps(LEVELS)};
  const VALIDATED = {json.dumps(data["VALIDATED"])};
  const PUBLISHED = {json.dumps(data["PUBLISHED"])};
  const COMPARE_LABEL = {json.dumps(data["COMPARE_LABEL"])};
  {script}
</script>
</body>
</html>
"""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scores", required=True)
    parser.add_argument("--compare")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--window", required=True)
    parser.add_argument("--compare-label", default="Aug 4")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    with open(args.scores, encoding="utf-8") as f:
        scores = json.load(f)
    compare = None
    if args.compare:
        with open(args.compare, encoding="utf-8") as f:
            compare = json.load(f)
    page = build(scores, compare, args.as_of, args.window, args.compare_label)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"Wrote {args.out}")
