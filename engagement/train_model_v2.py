"""Train and validate engagement scoring model v2 on GrowthZone history.

  python train_model_v2.py fetch --cache data/history        # read-only pull of memberships, purchases, org records
  python train_model_v2.py train --cache data/history        # writes scoring_model_v2.json + model_validation_v2.json

Every member active on Oct 1 of each year is described with data dated on or before that day and
labeled by whether it still had an active membership 12 months later. GrowthZone holds membership
history from 2016 and complete billing (events, dues payment dates) from 2019, so activity inputs
carry an 'unknown' indicator before the 2020 cohort and dues timing before 2017; tenure and size
learn from all ten years.

Two logistic models (L2-regularized): Affiliates, and contractors (Active + Associate pooled, with
type-specific size tiers and an Active adjustment, because Active members had only ten departures
in ten years). Each becomes a points scorecard per member type. Validation: leave-one-year-out and
an out-of-time test (train 2016-2022, test 2023-2025), against the 2026 scorecard where available.
Training needs numpy and scikit-learn; scoring (model_v2.py) needs neither."""

import argparse
import collections
import datetime as dt
import glob
import json
import math
import os
import random
import sys

import growthzone as g
import model_v2 as mv

HERE = os.path.dirname(os.path.abspath(__file__))
SEGMENTS = {"Affiliate": ["Affiliate"], "contractors": ["Active", "Associate"]}
C_BY_SEGMENT = {"Affiliate": 1.0, "contractors": 0.1}
FIRST_COHORT, LAST_COHORT = 2016, 2025


# -- history cache ---------------------------------------------------------------

def cmd_fetch(args):
    from concurrent.futures import ThreadPoolExecutor
    config = g.load_config(args.config)
    gz = g.client(config, args)
    os.makedirs(os.path.join(args.cache, "purchases"), exist_ok=True)
    os.makedirs(os.path.join(args.cache, "orgs"), exist_ok=True)
    mems = list(gz.paged("/api/memberships/all"))
    json.dump(mems, open(os.path.join(args.cache, "memberships_all.json"), "w"))
    listing = gz.get("/api/purchase") or []
    listing = listing.get("Results", listing) if isinstance(listing, dict) else listing
    json.dump(listing, open(os.path.join(args.cache, "purchases_listing.json"), "w"))
    cids = sorted({m["ContactId"] for m in mems if g.member_type_of(m["Type"], config)})

    def org(cid):
        path = os.path.join(args.cache, "orgs", f"{cid}.json")
        if not os.path.exists(path):
            json.dump({"general": gz.get(f"/api/contacts/OrgGeneral/{cid}") or {},
                       "fields": gz.get(f"/api/contacts/{cid}/NotesAndFields") or {}}, open(path, "w"))

    def detail(pid):
        path = os.path.join(args.cache, "purchases", f"{pid}.json")
        if not os.path.exists(path):
            try:
                data = gz.get(f"/api/thirdparty/purchase/{pid}") or {}
            except g.GrowthZoneError as e:
                data = {"_error": str(e)[:80]}
            json.dump(data, open(path, "w"))

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(org, cids))
        list(pool.map(detail, [p["PurchaseId"] for p in listing]))
    print(f"Cached {len(mems)} memberships, {len(cids)} organizations, {len(listing)} purchases ({gz.calls} API calls)")


class History:
    def __init__(self, cache, config, extra_purchase_dirs=()):
        self.config = config
        mems = json.load(open(os.path.join(cache, "memberships_all.json")))
        self.by_c = collections.defaultdict(list)
        for m in mems:
            if g.member_type_of(m["Type"], config) and m["Status"] in ("Active", "Dropped"):
                self.by_c[m["ContactId"]].append(m)
        self.orgs = {int(os.path.basename(p)[:-5]): json.load(open(p)) for p in glob.glob(os.path.join(cache, "orgs", "*.json"))}
        self.person_to_org = {}
        for cid, rec in self.orgs.items():
            for c in rec["general"].get("Contacts") or []:
                if c.get("ContactId"):
                    self.person_to_org.setdefault(c["ContactId"], cid)
        when = {p["PurchaseId"]: g.parse_date(p.get("PurchaseDate")) for p in json.load(open(os.path.join(cache, "purchases_listing.json")))}
        seen, self.purchases = set(), []
        for folder in (os.path.join(cache, "purchases"),) + tuple(extra_purchase_dirs):
            for path in glob.glob(os.path.join(folder, "*.json")):
                pid = int(os.path.basename(path)[:-5])
                if pid in seen or not when.get(pid):
                    continue
                rec = json.load(open(path))
                if "_error" not in rec:
                    seen.add(pid)
                    self.purchases.append((when[pid], rec))
        self.dues_types = {t.lower() for t in config["purchases"]["dues_fee_types"]}
        self.event_types = {t.lower() for t in config["purchases"]["event_fee_types"]}

    def member_at(self, cid, T):
        live = [m for m in self.by_c[cid] if g.parse_date(m["StartDate"]) <= T
                and (g.parse_date(m["EndDate"]) is None or g.parse_date(m["EndDate"]) > T)]
        return max(live, key=lambda m: m["StartDate"]) if live else None

    def org_of(self, rec, members):
        cands = [rec.get("ContactId")] + [c.get("ContactId") for c in rec.get("Contacts") or []]
        cands = [int(c) for c in cands if c not in (None, "", "None")]
        org = next((c for c in cands if c in members), None)
        if org is None:
            org = next((self.person_to_org[c] for c in cands if c in self.person_to_org and self.person_to_org[c] in members), None)
        return org

    def cohort(self, T):
        start, later = T - dt.timedelta(days=365), T + dt.timedelta(days=365)
        members = {cid: m for cid in self.by_c if (m := self.member_at(cid, T))}
        agg = {cid: {"spend": 0.0, "last": None, "late": [], "unpaid": False} for cid in members}
        for when, rec in self.purchases:
            if not (start < when <= T):
                continue
            org = self.org_of(rec, members)
            if org is None:
                continue
            a = agg[org]
            for item in rec.get("LineItems") or []:
                fee = (item.get("FeeItemType") or "").lower()
                amount = float(item.get("Total") or 0)
                if fee in self.dues_types:
                    due = g.parse_date(rec.get("DueDate")) or g.parse_date(rec.get("InvoiceDate")) or when
                    if due <= T and amount > 0:
                        paid = g.payment_date(item, T)
                        if paid is None:
                            a["unpaid"] = True
                        else:
                            a["late"].append((paid - due).days)
                    continue
                a["spend"] += amount
                if amount > 0 or fee in self.event_types:
                    a["last"] = max(a["last"] or when, when)
        rows = []
        for cid, m in members.items():
            a = agg[cid]
            rec = self.orgs.get(cid, {"general": {}, "fields": {}})
            bargaining = any((c.get("CategoryListName") or "").lower() == "bargaining rights" and c.get("Name")
                             for c in rec["general"].get("Categories") or [])
            rows.append({"cohort": T.year, "cid": cid, "name": m["Name"], "type": g.member_type_of(m["Type"], self.config),
                         "type_name": m["Type"], "tier": mv.tier_millions(m["Type"]),
                         "years": T.year - g.parse_date(m["StartDate"]).year, "spend": round(a["spend"], 2),
                         "recency_days": (T - a["last"]).days if a["last"] else None,
                         "dues_status": mv.dues_status(a["late"], a["unpaid"]), "bargaining": bargaining,
                         "left": (self.member_at(cid, later) is None) if later <= dt.date.today() else None})
        return rows


# -- training ----------------------------------------------------------------------

def encode(r, segment):
    """One-hot training inputs. 'unknown' indicators cover years before GrowthZone held the data."""
    lab = mv.inputs(r)
    f = {f"tenure={lab['tenure']}": 1}
    if r["cohort"] >= 2020:
        f[f"spend={lab['spend']}"] = 1
    else:
        f["activity=unknown"] = 1
    f[f"recency={lab['recency'] if r['cohort'] >= 2021 else 'unknown'}"] = 1
    f[f"dues={lab['dues'] if r['cohort'] >= 2017 and r['dues_status'] != 'none' else 'unknown'}"] = 1
    if segment == "contractors":
        f[f"tier[{r['type']}]={lab['tier'] or 'unknown'}"] = 1
        f[f"bargaining={lab['bargaining']}"] = 1
        if r["type"] == "Active":
            f["type=Active"] = 1
    return f


def auc(pairs):
    """pairs: (risk, left). Probability a leaver has a higher risk than a stayer."""
    pos = [p for p, y in pairs if y]
    neg = [p for p, y in pairs if not y]
    if not pos or not neg:
        return None
    ranked = sorted([(p, 1) for p in pos] + [(p, 0) for p in neg])
    rank_sum, i = 0.0, 0
    while i < len(ranked):
        j = i
        while j < len(ranked) and ranked[j][0] == ranked[i][0]:
            j += 1
        rank_sum += sum(1 for k in range(i, j) if ranked[k][1]) * (i + j + 1) / 2
        i = j
    return (rank_sum - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def fit(rows, segment):
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    fs = [encode(r, segment) for r in rows]
    cols = sorted({k for f in fs for k in f})
    m = LogisticRegression(C=C_BY_SEGMENT[segment], max_iter=5000)
    m.fit(np.array([[f.get(c, 0) for c in cols] for f in fs]), np.array([int(r["left"]) for r in rows]))
    return m, cols


def predict(model, cols, rows, segment):
    import numpy as np
    return model.predict_proba(np.array([[encode(r, segment).get(c, 0) for c in cols] for r in rows]))[:, 1]


def scorecard(model, cols, member_type, segment):
    coef = dict(zip(cols, model.coef_[0]))
    intercept = float(model.intercept_[0]) + coef.get("type=Active", 0.0) * (member_type == "Active")
    groups = {"tenure": [b[0] for b in mv.TENURE], "spend": [b[0] for b in mv.SPEND],
              "recency": [b[0] for b in mv.RECENCY],
              "dues": (["paid on time", "paid 1-4 months late", "4+ months late or unpaid"] if member_type == "Affiliate"
                       else ["paid on time", "paid late or unpaid"]) + ["no dues invoice on record"]}
    keys = {"tenure": "tenure", "spend": "spend", "recency": "recency", "dues": "dues"}
    if segment == "contractors":
        groups["tier"] = [b[0] for b in mv.TIERS[member_type]]
        groups["bargaining"] = ["yes", "no"]
    card = {}
    for group, labels in groups.items():
        prefix = f"tier[{member_type}]" if group == "tier" else keys.get(group, group)
        card[group] = [{"label": lab, "coef": float(coef.get(f"{prefix}={lab if lab != 'no dues invoice on record' else 'unknown'}", 0.0))}
                       for lab in labels]
    total_range = sum(max(b["coef"] for b in bins) - min(b["coef"] for b in bins) for bins in card.values())
    scale = 100 / total_range
    for bins in card.values():
        top = max(b["coef"] for b in bins)
        for b in bins:
            b["points"] = round(scale * (top - b["coef"]), 1)
    anchor = intercept + sum(max(b["coef"] for b in bins) for bins in card.values())
    return {"intercept": intercept, "scale": scale, "anchor": anchor, "groups": card}


def cmd_train(args):
    config = g.load_config(args.config)
    hist = History(args.cache, config, args.extra_purchases or ())
    rows = [r for y in range(FIRST_COHORT, LAST_COHORT + 1) for r in hist.cohort(dt.date(y, 10, 1))]
    old = {}
    if args.old_scores and os.path.exists(args.old_scores):
        old = {(r["cohort"], r["cid"]): r for r in json.load(open(args.old_scores))}
    model_out = {"version": "2.0", "trained": dt.date.today().isoformat(),
                 "training_cohorts": f"Oct 1, {FIRST_COHORT} - Oct 1, {LAST_COHORT}",
                 "bands": {name: floor for name, floor in mv.BANDS}, "scorecards": {}}
    validation = {"history": {}, "segments": {}}
    for t in ("Active", "Associate", "Affiliate"):
        validation["history"][t] = {y: [sum(r["left"] for r in rows if r["type"] == t and r["cohort"] == y),
                                        sum(1 for r in rows if r["type"] == t and r["cohort"] == y)]
                                    for y in range(FIRST_COHORT, LAST_COHORT + 1)}
        validation["history"][t + "_tenure"] = {lab: [sum(r["left"] for r in rows if r["type"] == t and lo <= r["years"] <= hi),
                                                      sum(1 for r in rows if r["type"] == t and lo <= r["years"] <= hi)]
                                                for lab, lo, hi in mv.TENURE}
    for segment, types in SEGMENTS.items():
        rs = [r for r in rows if r["type"] in types]
        oof = {}
        for y in range(FIRST_COHORT, LAST_COHORT + 1):
            m, cols = fit([r for r in rs if r["cohort"] != y], segment)
            test = [r for r in rs if r["cohort"] == y]
            oof.update({(r["cohort"], r["cid"]): p for r, p in zip(test, predict(m, cols, test, segment))})
        m, cols = fit([r for r in rs if r["cohort"] <= 2022], segment)
        test = [r for r in rs if r["cohort"] >= 2023]
        oot = {(r["cohort"], r["cid"]): p for r, p in zip(test, predict(m, cols, test, segment))}
        modern = [r for r in rs if r["cohort"] >= 2020]
        seg = {"member_years": len(rs), "left": sum(r["left"] for r in rs),
               "auc_new_2020_2025": auc([(oof[(r["cohort"], r["cid"])], r["left"]) for r in modern]),
               "auc_new_out_of_time": auc([(oot[(r["cohort"], r["cid"])], r["left"]) for r in test]),
               "by_type": {}, "calibration": []}
        if old:
            both = [r for r in modern if (r["cohort"], r["cid"]) in old]
            seg["auc_old_2020_2025"] = auc([(-old[(r["cohort"], r["cid"])]["score"], r["left"]) for r in both])
            seg["auc_old_out_of_time"] = auc([(-old[(r["cohort"], r["cid"])]["score"], r["left"]) for r in test if (r["cohort"], r["cid"]) in old])
            of = [r for r in both if old[(r["cohort"], r["cid"])]["level"] in ("Moderate Risk", "High Risk")]
            seg["old_flagged"] = [len(of), sum(r["left"] for r in of), len(both), sum(r["left"] for r in both)]
        nf = [r for r in modern if oof[(r["cohort"], r["cid"])] >= 0.07]
        seg["new_flagged"] = [len(nf), sum(r["left"] for r in nf), len(modern), sum(r["left"] for r in modern)]
        for t in types:
            mt = [r for r in modern if r["type"] == t]
            seg["by_type"][t] = {"auc_new": auc([(oof[(r["cohort"], r["cid"])], r["left"]) for r in mt]),
                                 "auc_old": auc([(-old[(r["cohort"], r["cid"])]["score"], r["left"]) for r in mt if (r["cohort"], r["cid"]) in old]) if old else None,
                                 "left": sum(r["left"] for r in mt), "member_years": len(mt)}
        for name, floor in mv.BANDS:
            ceiling = min([f for _, f in mv.BANDS if f > floor] or [1.01])
            b = [r for r in rs if floor <= oof[(r["cohort"], r["cid"])] < ceiling]
            seg["calibration"].append({"band": name, "member_years": len(b), "left": sum(r["left"] for r in b),
                                       "predicted": sum(oof[(r["cohort"], r["cid"])] for r in b) / len(b) if b else None})
        validation["segments"][segment] = seg
        final, cols = fit(rs, segment)
        for t in types:
            model_out["scorecards"][t] = scorecard(final, cols, t, segment)
        print(f"{segment}: AUC 2020-25 {seg['auc_new_2020_2025']:.3f} (old {seg.get('auc_old_2020_2025') or 0:.3f}), "
              f"out-of-time {seg['auc_new_out_of_time']:.3f} (old {seg.get('auc_old_out_of_time') or 0:.3f})")
    with open(mv.MODEL_FILE, "w") as f:
        json.dump(model_out, f, indent=1)
    os.makedirs(os.path.dirname(os.path.abspath(args.validation)), exist_ok=True)
    with open(args.validation, "w") as f:
        json.dump(validation, f, indent=1)
    print(f"Wrote {mv.MODEL_FILE} and {args.validation}")


def main():
    parser = argparse.ArgumentParser(description="Train engagement scoring model v2.")
    parser.add_argument("--config", default=os.path.join(HERE, "growthzone_config.json"))
    sub = parser.add_subparsers(dest="command", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--cache", default=os.path.join(HERE, "data", "history"))
    f.add_argument("--workers", type=int, default=8)
    t = sub.add_parser("train")
    t.add_argument("--cache", default=os.path.join(HERE, "data", "history"))
    t.add_argument("--extra-purchases", nargs="*", help="more purchase-detail folders (e.g. data/cache/purchases)")
    t.add_argument("--old-scores", help="JSON list of {cohort, cid, score, level} from the 2026 scorecard back-test")
    t.add_argument("--validation", default=os.path.join(HERE, "model_validation_v2.json"))
    args = parser.parse_args()
    {"fetch": cmd_fetch, "train": cmd_train}[args.command](args)


if __name__ == "__main__":
    main()
