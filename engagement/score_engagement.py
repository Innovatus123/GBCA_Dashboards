"""GBCA member engagement scoring - validation and corrected rescoring.

Reads the three normalized GrowthZone "GBCA Member Engagement Report" extracts
(Active, Associate, Affiliate) and scores every member two ways:

  reported  - reproduces the model behind the 2026.08.04 risk-analysis files,
              including its defects, to prove we understand how the published
              numbers were produced.
  corrected - applies the 2026 scorecards as written.

Input files are pipe-delimited with this header (member data is NOT stored in
this repository; point --data at a local folder):

  name|years|individuals|events|mem_spend|non_spend|committee|issue|content|bargaining|rep_score|rep_risk

  committee:  "" none, "C" committee only, "B" Board only, "BC" Board + committee
  issue/content/bargaining: "1" if the GrowthZone field is populated
  rep_score/rep_risk: score and level from the published risk-analysis file

Usage:  python score_engagement.py --data <folder> [--json out.json]
"""

import argparse
import csv
import json
import math
import os
from collections import Counter

LEVELS = ["Highly Engaged", "Engaged", "Low Risk", "Moderate Risk", "High Risk"]

# Upper bound (inclusive) of each risk band. Decimal scores between bands
# (e.g. 40.2) fall into the higher band, matching the published model.
BANDS = {
    "Active": [(20, "High Risk"), (40, "Moderate Risk"), (75, "Low Risk"), (85, "Engaged")],
    "Associate": [(20, "High Risk"), (40, "Moderate Risk"), (75, "Low Risk"), (85, "Engaged")],
    "Affiliate": [(20, "High Risk"), (40, "Moderate Risk"), (65, "Low Risk"), (85, "Engaged")],
}


def num(value):
    return float(value) if value not in ("", None) else None


def flag(value):
    return value not in ("", None, "0")


def classify(member_type, score):
    for upper, level in BANDS[member_type]:
        if score <= upper:
            return level
    return "Highly Engaged"


def dues_tier(mem_spend):
    if mem_spend is None:
        return 0
    if mem_spend > 5000:
        return 10
    if mem_spend >= 2000:
        return 5
    return 0


def score_active(m, corrected):
    """Active scorecard: 30 core / 35 participation / 25 financial / 10 additional."""
    years, events, spend = num(m["years"]), num(m["events"]), num(m["non_spend"])
    s = min(2 * (years or 0), 15)
    s += 15 if flag(m["bargaining"]) else 0
    if corrected:
        s += 13 if "B" in m["committee"] else 0
        s += min(2 * events, 12) if events is not None else 0
        s += min(spend / 1000, 15) if spend is not None else 0
    else:
        # Published model: 13 Board points granted to every member, and a blank
        # event count or blank non-dues spend earns the category maximum.
        s += 13
        s += min(2 * events, 12) if events is not None else 12
        s += min(spend / 1000, 15) if spend is not None else 15
    s += 10 if m["committee"] else 0
    s += dues_tier(num(m["mem_spend"]))
    s += 5 if flag(m["content"]) else 0
    s += 5 if flag(m["issue"]) else 0
    return s


def score_associate(m, corrected):
    """Associate scorecard: 30 core / 30 participation / 28 financial / 10 additional (98 max)."""
    s = min(2 * (num(m["years"]) or 0), 15)
    s += 15 if flag(m["bargaining"]) else 0
    s += 15 if m["committee"] else 0
    s += min(2 * (num(m["events"]) or 0), 15)
    s += min(math.floor((num(m["non_spend"]) or 0) / 1000), 18)
    s += dues_tier(num(m["mem_spend"]))
    s += 5 if flag(m["content"]) else 0
    s += 5 if flag(m["issue"]) else 0
    return s


def score_affiliate(m, corrected):
    """Affiliate scorecard: 15 core / 40 participation / 35 financial / 10 additional."""
    s = min(3 * (num(m["years"]) or 0), 15)
    s += 12 if m["committee"] else 0
    s += min(2 * (num(m["events"]) or 0), 20)
    s += min(num(m["individuals"]) or 0, 8)
    s += min((num(m["non_spend"]) or 0) / 1000, 30)
    s += 5 if num(m["mem_spend"]) == 1350 else 0
    s += 5 if flag(m["content"]) else 0
    s += 5 if flag(m["issue"]) else 0
    return s


SCORERS = {"Active": score_active, "Associate": score_associate, "Affiliate": score_affiliate}
FILES = {"Active": "active.psv", "Associate": "associate.psv", "Affiliate": "affiliate.psv"}

# The published chart also counted the two GrowthZone report footer rows
# ("Count\Average\Totals" and "Generated <date> by ...") as members.
FOOTER_ROWS = {
    "Active": ["Low Risk", "Low Risk"],
    "Associate": [],
    "Affiliate": ["Low Risk", "High Risk"],
}


def load(folder, member_type):
    with open(os.path.join(folder, FILES[member_type]), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="|"))


def run(folder):
    result = {"types": {}, "mismatches": []}
    for member_type, scorer in SCORERS.items():
        rows = []
        for m in load(folder, member_type):
            reported = round(scorer(m, corrected=False), 2)
            corrected = round(scorer(m, corrected=True), 2)
            if abs(reported - float(m["rep_score"])) > 0.06 or classify(member_type, reported) != m["rep_risk"]:
                result["mismatches"].append((member_type, m["name"], reported, m["rep_score"], m["rep_risk"]))
            rows.append({
                "name": m["name"],
                "reported_score": float(m["rep_score"]),
                "reported_level": m["rep_risk"],
                "corrected_score": corrected,
                "corrected_level": classify(member_type, corrected),
                "years": num(m["years"]) or 0,
                "events": num(m["events"]) or 0,
                "non_spend": num(m["non_spend"]) or 0,
                "committee": m["committee"],
                "blank_events": m["events"] == "",
                "blank_spend": m["non_spend"] == "",
                "dues_populated": m["mem_spend"] != "",
            })
        published = Counter(r["reported_level"] for r in rows) + Counter(FOOTER_ROWS[member_type])
        result["types"][member_type] = {
            "members": rows,
            "published": {lvl: published.get(lvl, 0) for lvl in LEVELS},
            "reported": {lvl: sum(r["reported_level"] == lvl for r in rows) for lvl in LEVELS},
            "corrected": {lvl: sum(r["corrected_level"] == lvl for r in rows) for lvl in LEVELS},
        }
    return result


def pct(n, d):
    return f"{100 * n / d:.1f}%" if d else "-"


def print_summary(result):
    for view in ("published", "reported", "corrected"):
        print(f"\n== {view.upper()} ==")
        total = Counter()
        for member_type, t in result["types"].items():
            n = sum(t[view].values())
            total.update(t[view])
            print(f"{member_type:10} n={n:3}  " + "  ".join(f"{lvl[:4]} {t[view][lvl]:3} ({pct(t[view][lvl], n)})" for lvl in LEVELS))
        n = sum(total.values())
        at_risk = total["Moderate Risk"] + total["High Risk"]
        print(f"{'Overall':10} n={n:3}  " + "  ".join(f"{lvl[:4]} {total[lvl]:3} ({pct(total[lvl], n)})" for lvl in LEVELS))
        print(f"           Moderate + High Risk: {at_risk} ({pct(at_risk, n)})")
    print(f"\nReproduction mismatches: {len(result['mismatches'])}")
    for mismatch in result["mismatches"]:
        print("  ", mismatch)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", required=True, help="folder holding active.psv, associate.psv, affiliate.psv")
    parser.add_argument("--json", help="optional path to write full member-level results")
    args = parser.parse_args()
    output = run(args.data)
    print_summary(output)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)
