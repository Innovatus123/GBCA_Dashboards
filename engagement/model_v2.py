"""Engagement scoring model v2: segment-specific scorecards trained on ten years of renewals.

Each member gets
  score    0-100 engagement points (higher = more engaged), from the scorecard for its type
  risk     calibrated probability of leaving within 12 months
  band     Secure (<3%), Stable (3-7%), Watch (7-15%), At Risk (15%+)
  reasons  the inputs that cost the most points

Inputs (all observable in GrowthZone on the scoring date):
  years       calendar years since the current membership started (GrowthZone's rule)
  spend       non-dues spend in the last 12 months (events, sponsorships, training)
  recency     time since the last event registration or non-dues purchase
  dues        timing of the last 12 months' dues payment
  tier        dollar-volume tier in the membership type name (Active and Associate)
  bargaining  bargaining rights on file (Active and Associate)

Weights live in scoring_model_v2.json, written by train_model_v2.py. Committee seats are not
scored: GrowthZone keeps only current rosters, so their effect cannot be measured as of a past
date without look-ahead bias."""

import json
import math
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_FILE = os.path.join(HERE, "scoring_model_v2.json")

TENURE = [("first two years", 0, 1), ("2-4 years", 2, 4), ("5-9 years", 5, 9), ("10-19 years", 10, 19), ("20+ years", 20, 10 ** 6)]
SPEND = [("under $1K", 0, 999.99), ("$1K-5K", 1000, 4999.99), ("$5K+", 5000, 1e12)]
RECENCY = [("within 6 months", 0, 182), ("6-12 months ago", 183, 365), ("none in 12 months", 366, 10 ** 9)]
TIERS = {"Associate": [("under $2M", 0, 1.99), ("$2M+", 2, 1e9)],
         "Active": [("under $10M", 0, 9.99), ("$10M+", 10, 1e9)]}
BANDS = [("At Risk", 0.15), ("Watch", 0.07), ("Stable", 0.03), ("Secure", 0.0)]
GROUP_LABELS = {"tenure": "Tenure", "spend": "Non-dues spend, last 12 months", "recency": "Last event or purchase",
                "dues": "Dues payment, last 12 months", "tier": "Size tier", "bargaining": "Bargaining rights"}


def bin_of(bins, value):
    return next(lab for lab, lo, hi in bins if lo <= value <= hi)


def tier_millions(type_name):
    """Lower bound of the dollar-volume tier in a membership type name, in $ millions (None if absent)."""
    text = type_name or ""
    over = re.search(r"over \$?([\d,\.]+)", text, re.I)
    if over:
        return float(over.group(1).replace(",", ""))
    m = re.search(r"\$([\d,\.]+)\s*(million)?", text, re.I)
    if not m:
        return None
    value = float(m.group(1).replace(",", ""))
    return value if m.group(2) else value / 1_000_000


def dues_status(lateness_days, unpaid):
    """lateness_days: days between due date and payment for each dues invoice due in the window."""
    if unpaid:
        return "unpaid"
    if not lateness_days:
        return "none"
    worst = max(lateness_days)
    return "on_time" if worst <= 30 else ("late" if worst <= 120 else "very_late")


def dues_label(member_type, status):
    if status == "none":
        return "no dues invoice on record"
    if member_type == "Affiliate":
        return {"on_time": "paid on time", "late": "paid 1-4 months late"}.get(status, "4+ months late or unpaid")
    return "paid on time" if status == "on_time" else "paid late or unpaid"


def inputs(member):
    """member: dict with type, years, spend, recency_days, dues_status, tier, bargaining -> {group: bin label}."""
    t = member["type"]
    rec = member.get("recency_days")
    out = {"tenure": bin_of(TENURE, int(member["years"] or 0)),
           "spend": bin_of(SPEND, float(member.get("spend") or 0)),
           "recency": bin_of(RECENCY, 10 ** 6 if rec in (None, "") else int(rec)),
           "dues": dues_label(t, member.get("dues_status") or "none")}
    if t in TIERS:
        tier = member.get("tier")
        out["tier"] = bin_of(TIERS[t], float(tier)) if tier not in (None, "") else None
        out["bargaining"] = "yes" if member.get("bargaining") else "no"
    return out


def load_model(path=MODEL_FILE):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def score_member(member, model):
    card = model["scorecards"][member["type"]]
    chosen = inputs(member)
    logit, points, lost = card["intercept"], 0.0, []
    for group, label in chosen.items():
        bins = card["groups"][group]
        if label is None:  # no tier in the type name: use the group's average weight, average points
            coef = sum(b["coef"] for b in bins) / len(bins)
            pts = sum(b["points"] for b in bins) / len(bins)
        else:
            b = next(b for b in bins if b["label"] == label)
            coef, pts = b["coef"], b["points"]
        logit += coef
        points += pts
        best = max(b["points"] for b in bins)
        if best - pts >= 1:
            lost.append((best - pts, f"{GROUP_LABELS[group]}: {label or 'unknown'}"))
    risk = 1 / (1 + math.exp(-logit))
    band = next(name for name, floor in BANDS if risk >= floor)
    return {"score": round(points), "risk": risk, "band": band, "inputs": chosen,
            "reasons": [text for _, text in sorted(lost, reverse=True)[:3]]}


def band_thresholds(model, member_type):
    """Score at or below which a member of this type falls into each band (scores fall as risk rises)."""
    card = model["scorecards"][member_type]
    out = {}
    for name, floor in BANDS[:-1]:
        x = math.log(floor / (1 - floor))
        out[name] = card["scale"] * (card["anchor"] - x)
    return out


def score_folder(folder, model=None):
    """Score every member in <folder>/features_v2.csv (written by growthzone.py pull)."""
    import csv
    model = model or load_model()
    out = []
    with open(os.path.join(folder, "features_v2.csv"), newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            member = {"type": row["type"], "years": int(row["years"] or 0), "spend": float(row["spend"] or 0),
                      "recency_days": int(row["recency_days"]) if row["recency_days"] not in ("", None) else None,
                      "dues_status": row["dues_status"], "tier": float(row["tier"]) if row["tier"] not in ("", None) else None,
                      "bargaining": row["bargaining"] == "1"}
            result = score_member(member, model)
            out.append({"cid": int(row["cid"]), "name": row["name"], "type": row["type"], "years": member["years"],
                        "dues": float(row["dues"] or 0), "events": int(row["events"] or 0), "committee": row["committee"],
                        **result})
    return out


def main():
    import argparse
    import collections
    parser = argparse.ArgumentParser(description="Score members with engagement model v2.")
    parser.add_argument("--data", required=True, help="folder holding features_v2.csv")
    parser.add_argument("--json", help="write scores here")
    args = parser.parse_args()
    scores = score_folder(args.data)
    for t in ("Active", "Associate", "Affiliate"):
        rows = [s for s in scores if s["type"] == t]
        bands = collections.Counter(s["band"] for s in rows)
        print(f"{t:10} n={len(rows):3}  " + "  ".join(f"{b} {bands.get(b, 0):3}" for b, _ in BANDS)
              + f"  expected to leave {sum(s['risk'] for s in rows):.1f}")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"model": load_model()["version"], "members": scores}, f, indent=1)
        print(f"Wrote {args.json}")


if __name__ == "__main__":
    main()
