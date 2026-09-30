"""Pull GBCA member engagement data from GrowthZone.

Commands
  check        Confirm the API credential works and show member counts by type.
  discover     Save raw samples of every endpoint the pull uses (memberships,
               custom fields, related contacts, groups, activities, purchases,
               saved reports) and list the custom-field names GrowthZone returns,
               so the field mapping in growthzone_config.json can be confirmed.
  pull         Rebuild the "GBCA Member Engagement Report" from the API, write it
               in the same 17-column layout GrowthZone exports, then write the
               normalized files score_engagement.py reads.
  from-export  Normalize a GrowthZone report export (.csv, or .xlsx with openpyxl)
               into the files score_engagement.py reads. Report footer lines
               ("Count\\Average\\Totals", "Generated ... by ...") are dropped.

Credentials (never commit them)
  GROWTHZONE_API_KEY       API key from GrowthZone > Settings > Advanced Settings >
                           API Key Permissions. Sent as "Authorization: ApiKey <key>".
  GROWTHZONE_ACCESS_TOKEN  Alternative: an OAuth access token, sent as Bearer.
  GROWTHZONE_BASE_URL      Optional override of base_url in growthzone_config.json.

Examples
  python growthzone.py check
  python growthzone.py discover --out data/discovery
  python growthzone.py pull --out data/2026-10-01
  python growthzone.py from-export --active a.csv --associate b.csv --affiliate c.csv --out data/2026-10-01
  python score_engagement.py --data data/2026-10-01
"""

import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
TYPES = ("Active", "Associate", "Affiliate")

# Column layout of the GrowthZone "GBCA Member Engagement Report" export.
REPORT_COLUMNS = [
    "Contact Name", "Member Spotlights", "Member Recognition Awards", "Membership Type",
    "Years as a Member", "Active Individuals with Business", "Count of Event Attendees",
    "Membership Spend", "Non-Membership Spend", "All Committee Participation",
    "Tuition Reimbursement", "Issue Resolution Assistance", "Content Contributor",
    "Hosted/Utilized Meeting Space", "GBCA Vendor", "Special Member Programs", "All Bargaining Rights",
]
SCORED_FIELDS = ["Years as a Member", "Count of Event Attendees", "Non-Membership Spend",
                 "All Committee Participation", "All Bargaining Rights"]
PSV_HEADER = ["name", "years", "individuals", "events", "mem_spend", "non_spend",
              "committee", "issue", "content", "bargaining", "rep_score", "rep_risk"]


def load_config(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class GrowthZoneError(RuntimeError):
    pass


class GrowthZone:
    """Minimal read-only GrowthZone REST client (stdlib only)."""

    def __init__(self, base_url, api_key=None, access_token=None, pause=0.15):
        if not (api_key or access_token):
            raise GrowthZoneError(
                "No GrowthZone credential found. Set GROWTHZONE_API_KEY (or GROWTHZONE_ACCESS_TOKEN) "
                "in the environment; see engagement/README.md.")
        self.base_url = base_url.rstrip("/")
        self.auth = f"ApiKey {api_key}" if api_key else f"Bearer {access_token}"
        self.pause = pause
        self.calls = 0

    def get(self, path, params=None, method="GET", body=None):
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params, safe="$")
        data = json.dumps(body).encode() if body is not None else None
        for attempt in range(5):
            req = urllib.request.Request(url, data=data, method=method, headers={
                "Authorization": self.auth, "Accept": "application/json", "Content-Type": "application/json"})
            try:
                self.calls += 1
                with urllib.request.urlopen(req, timeout=60) as resp:
                    raw = resp.read()
                time.sleep(self.pause)
                return json.loads(raw) if raw else None
            except urllib.error.HTTPError as e:
                if e.code in (401, 403):
                    raise GrowthZoneError(
                        f"{e.code} from {path}: the credential was rejected or lacks permission for this "
                        "endpoint. Check the key's API Key Permissions in GrowthZone.") from None
                if e.code in (429, 500, 502, 503, 504) and attempt < 4:
                    time.sleep(float(e.headers.get("Retry-After") or 2 ** attempt))
                    continue
                raise GrowthZoneError(f"{e.code} from {path}: {e.read()[:300]!r}") from None
            except urllib.error.URLError as e:
                if attempt < 4:
                    time.sleep(2 ** attempt)
                    continue
                raise GrowthZoneError(f"Could not reach {self.base_url}: {e.reason}") from None

    def paged(self, path, page_size=100, limit=None):
        """Yield rows from ListViewReturnModel endpoints ($top/$skip paging)."""
        skip = 0
        while True:
            page = self.get(path, {"$top": page_size, "$skip": skip})
            rows = page.get("Results", []) if isinstance(page, dict) else (page or [])
            yield from rows
            skip += len(rows)
            total = page.get("TotalRecordAvailable") if isinstance(page, dict) else None
            if not rows or len(rows) < page_size or (total is not None and skip >= total):
                return
            if limit and skip >= limit:
                return


# -- value helpers -------------------------------------------------------------

def parse_date(value):
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")[:19]).date()
    except ValueError:
        return None


def years_since(start, today):
    return today.year - start.year - ((today.month, today.day) < (start.month, start.day))


def years_from_active_for(text):
    match = re.search(r"(\d+)\s*year", text or "", re.I)
    return int(match.group(1)) if match else None


def money(value):
    if value in (None, ""):
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", str(value))
    return float(cleaned) if cleaned not in ("", "-", ".") else None


def custom_field_text(field):
    """Render a CustomFieldTabModel value as the comma-joined text GrowthZone exports."""
    value = field.get("Value")
    if value in (None, "", [], {}):
        return ""
    options = {str(o.get("id")): o.get("name") for o in field.get("SelectListDataArray") or []}
    items = value if isinstance(value, list) else [value]
    out = []
    for item in items:
        if isinstance(item, dict):
            item = item.get("Name") or item.get("name") or item.get("Value") or item.get("value") or ""
        text = options.get(str(item), item)
        if text not in (None, "", False):
            out.append(str(text))
    return ", ".join(out)


# -- normalization shared by pull and from-export ------------------------------

FOOTER = re.compile(r"^(count\\average\\totals|generated\s)", re.I)


def member_type_of(text, config):
    if text in config["membership_types"]:
        return config["membership_types"][text]
    for t in TYPES:
        if re.search(rf"\b{t}\b", text or "", re.I):
            return t
    return None


def normalize(rows, config):
    """Report-shaped dicts -> {member type: [PSV rows]}; drops footer and non-member lines."""
    out = {t: [] for t in TYPES}
    board = [s.lower() for s in config["committee_groups"]["board"]]
    for r in rows:
        name = (r.get("Contact Name") or "").strip()
        mtype = member_type_of(r.get("Membership Type"), config)
        if not name or FOOTER.match(name) or not mtype:
            continue
        cmte = (r.get("All Committee Participation") or "").lower()
        has_board = any(b in cmte for b in board)
        has_cmte = bool(cmte.replace(",", "").strip()) and (not has_board or "committee" in cmte)
        committee = ("B" if has_board else "") + ("C" if has_cmte else "")
        spend = money(r.get("Non-Membership Spend"))
        dues = money(r.get("Membership Spend"))
        num = lambda k: "" if str(r.get(k, "")).strip() == "" else str(int(float(r[k])))
        out[mtype].append({
            "name": name,
            "years": num("Years as a Member"),
            "individuals": num("Active Individuals with Business"),
            "events": num("Count of Event Attendees"),
            "mem_spend": "" if dues is None else f"{dues:g}",
            "non_spend": "" if spend is None else f"{spend:g}",
            "committee": committee,
            "issue": "1" if (r.get("Issue Resolution Assistance") or "").strip() else "",
            "content": "1" if (r.get("Content Contributor") or "").strip() else "",
            "bargaining": "1" if (r.get("All Bargaining Rights") or "").strip() else "0",
            "rep_score": "",
            "rep_risk": "",
        })
    return out


def write_outputs(out_dir, report_rows, normalized):
    os.makedirs(out_dir, exist_ok=True)
    if report_rows is not None:
        with open(os.path.join(out_dir, "engagement_report.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["GrowthZone Contact Id"] + REPORT_COLUMNS, extrasaction="ignore")
            w.writeheader()
            w.writerows(report_rows)
    for t in TYPES:
        with open(os.path.join(out_dir, f"{t.lower()}.psv"), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=PSV_HEADER, delimiter="|")
            w.writeheader()
            w.writerows(normalized[t])


def load_baseline(config):
    """Totals from the last validated export, kept in a git-ignored local file (the repo is public)."""
    path = os.path.join(HERE, config.get("baseline_file", ""))
    if not config.get("baseline_file") or not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def reconcile(report_rows, config):
    """Coverage and totals versus the last validated export. Returns problems that block scoring."""
    base = load_baseline(config)
    problems = []
    vs = lambda key, t, fmt: f" vs {base[key][t]:{fmt}}" if base else ""
    print(f"\nPulled totals" + (f" vs {base['label']}" if base else " (no baseline file; see README)"))
    print(f"{'Type':10} {'Members':>14} {'Event attendees':>20} {'Non-dues spend':>24}")
    for t in TYPES:
        rows = [r for r in report_rows if member_type_of(r.get("Membership Type"), config) == t]
        ev = sum(int(r["Count of Event Attendees"] or 0) for r in rows if str(r["Count of Event Attendees"]) != "")
        sp = sum(money(r["Non-Membership Spend"]) or 0 for r in rows)
        print(f"{t:10} {len(rows):6}{vs('members', t, '4')} {ev:11}{vs('event_attendees', t, '5')} "
              f"{sp:14,.0f}{vs('non_dues_spend', t, '8,')}")
    print("\nField coverage (members with a non-zero value):")
    for col in REPORT_COLUMNS[1:]:
        filled = sum(1 for r in report_rows if str(r.get(col, "")).strip() not in ("", "0", "0.0", "0.00"))
        share = filled / len(report_rows) if report_rows else 0
        flag = ""
        if col in SCORED_FIELDS and filled == 0:
            flag = "  <- scored field has no data"
            problems.append(col)
        elif col == "Membership Spend" and filled == 0:
            flag = "  <- dues points will not be awarded"
        print(f"  {col:34} {filled:4} / {len(report_rows)}  {share:6.1%}{flag}")
    return problems


# -- commands ------------------------------------------------------------------

def client(config, args):
    base = os.environ.get("GROWTHZONE_BASE_URL") or config["base_url"]
    return GrowthZone(base, os.environ.get("GROWTHZONE_API_KEY"), os.environ.get("GROWTHZONE_ACCESS_TOKEN"))


def cmd_check(config, args):
    gz = client(config, args)
    types = list(gz.paged("/api/memberships/types"))
    print(f"Connected to {gz.base_url}: {len(types)} membership types")
    for t in types:
        mapped = config["membership_types"].get(t.get("Name"), "")
        print(f"  {t.get('Name', '?'):40} active memberships: {t.get('ActiveMembershipCount', '?'):>5}  {mapped}")
    missing = set(config["membership_types"]) - {t.get("Name") for t in types}
    if missing:
        print(f"Config names not found in GrowthZone: {sorted(missing)}")


def active_members(gz, config, today):
    """ContactId -> {name, type, years} for current members of the mapped types."""
    statuses = {s.lower() for s in config["active_membership_statuses"]}
    members, earliest = {}, {}
    for m in gz.paged("/api/memberships/all"):
        type_name = m.get("Type") if m.get("Type") in config["membership_types"] else m.get("Name")
        mtype = config["membership_types"].get(type_name)
        cid = m.get("ContactId")
        start = parse_date(m.get("StartDate"))
        if cid and start and mtype:
            earliest[cid] = min(start, earliest.get(cid, start))
        if not (cid and mtype and (m.get("Status") or "").lower() in statuses):
            continue
        members[cid] = {"type": mtype, "type_name": type_name, "name": m.get("Name"),
                        "active_for": years_from_active_for(m.get("MembershipActiveFor"))}
    for cid, m in members.items():
        signals = [m["active_for"], years_since(earliest[cid], today) if cid in earliest else None]
        signals = [y for y in signals if y is not None]
        m["years"] = max(signals) if signals else None
    return members


def cmd_discover(config, args):
    gz = client(config, args)
    os.makedirs(args.out, exist_ok=True)

    def save(name, obj):
        with open(os.path.join(args.out, name + ".json"), "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, default=str)

    today = dt.date.today()

    memberships = list(gz.paged("/api/memberships/all"))
    save("memberships_all", memberships)
    by = {}
    for m in memberships:
        by.setdefault((m.get("Type"), m.get("Status")), 0)
        by[(m.get("Type"), m.get("Status"))] += 1
    print("Memberships by type and status:")
    for (t, s), n in sorted(by.items(), key=lambda x: (str(x[0][0]), str(x[0][1]))):
        print(f"  {str(t):40} {str(s):15} {n:5}")

    members = active_members(gz, config, today)
    print(f"\nCurrent members of mapped types: {len(members)}")
    sample = list(members)[: args.samples]
    field_names = {}
    for cid in sample:
        fields = gz.get(f"/api/contacts/{cid}/NotesAndFields")
        general = gz.get(f"/api/contacts/OrgGeneral/{cid}")
        save(f"contact_{cid}_fields", fields)
        save(f"contact_{cid}_orggeneral", general)
        for f in (fields or {}).get("Fields") or []:
            key = f.get("DisplayName") or f.get("Name")
            field_names.setdefault(key, set()).add(custom_field_text(f)[:60])
    print("\nCustom fields on sampled member records (name: sample values):")
    for k in sorted(field_names, key=str):
        print(f"  {k}: {sorted(v for v in field_names[k] if v)[:3]}")

    for name, path in [("purchases", "/api/purchase"), ("easyquery_custom_reports", "/api/easyquery/customreports"),
                       ("report_catalog", "/api/reporting/tenantreports")]:
        try:
            save(name, gz.get(path))
            print(f"Saved {name}")
        except GrowthZoneError as e:
            print(f"{name}: {e}")
    print(f"\nRaw samples written to {args.out} ({gz.calls} API calls). Keep this folder out of git.")


def purchases_by_member(gz, config, member_names):
    """Normalized display name -> (dues total, non-dues total) inside the purchase window."""
    start = parse_date(config["purchases"]["window_start"])
    dues_match = [s.lower() for s in config["purchases"]["dues_type_match"]]
    totals = {}
    rows = gz.get("/api/purchase") or []
    rows = rows.get("Results", rows) if isinstance(rows, dict) else rows
    for p in rows:
        when = parse_date(p.get("PurchaseDate"))
        key = norm_name(p.get("ContactDisplayName"))
        if not when or when < start or key not in member_names:
            continue
        dues, other = totals.get(key, (0.0, 0.0))
        amount = float(p.get("Total") or 0)
        if any(s in (p.get("PurchaseType") or "").lower() for s in dues_match):
            dues += amount
        else:
            other += amount
        totals[key] = (dues, other)
    return totals


def norm_name(text):
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def event_count(general, config):
    if config["events"]["source"] != "activities":
        return None
    start = parse_date(config["events"]["window_start"])
    words = [w.lower() for w in config["events"]["activity_match"]]
    count = 0
    for a in (general or {}).get("Activities") or []:
        when = parse_date(a.get("ActivityDate"))
        if when and when >= start and any(w in (a.get("Description") or "").lower() for w in words):
            count += 1
    return count


def cmd_pull(config, args):
    gz = client(config, args)
    today = dt.date.today()
    members = active_members(gz, config, today)
    print(f"{len(members)} current members of mapped types")

    board = config["committee_groups"]["board"]
    committee_words = config["committee_groups"]["committee"]
    report_rows = []
    for i, (cid, m) in enumerate(sorted(members.items(), key=lambda x: x[1]["name"] or ""), 1):
        fields = gz.get(f"/api/contacts/{cid}/NotesAndFields") or {}
        general = gz.get(f"/api/contacts/OrgGeneral/{cid}") or {}
        by_name = {}
        for f in fields.get("Fields") or []:
            for key in (f.get("DisplayName"), f.get("Name")):
                if key:
                    by_name[key.lower()] = custom_field_text(f)
        name = general.get("ContactDisplayName") or m["name"]
        row = {"GrowthZone Contact Id": cid, "Contact Name": name, "Membership Type": m["type_name"],
               "Years as a Member": "" if m["years"] is None else m["years"],
               "Active Individuals with Business": len(general.get("Contacts") or [])}
        for column, candidates in config["custom_fields"].items():
            row[column] = next((by_name[c.lower()] for c in candidates if by_name.get(c.lower())), "")
        if not row["All Committee Participation"]:
            groups = [g.get("Name") or "" for g in general.get("Groups") or []]
            labels = []
            if any(b.lower() in g.lower() for g in groups for b in board):
                labels.append("Board of Directors")
            if any(w.lower() in g.lower() for g in groups for w in committee_words):
                labels.append("Committee Participation")
            row["All Committee Participation"] = ",".join(labels)
        events = event_count(general, config)
        row["Count of Event Attendees"] = "" if events is None else events
        report_rows.append(row)
        if i % 25 == 0:
            print(f"  {i}/{len(members)} members pulled ({gz.calls} API calls)")

    try:
        spend = purchases_by_member(gz, config, {norm_name(r["Contact Name"]) for r in report_rows})
        for row in report_rows:
            dues, other = spend.get(norm_name(row["Contact Name"]), (0.0, 0.0))
            row["Membership Spend"] = f"{dues:.2f}" if dues else ""
            row["Non-Membership Spend"] = f"{other:.2f}" if other else "0"
    except GrowthZoneError as e:
        print(f"Purchases unavailable, spend left blank: {e}")

    problems = reconcile(report_rows, config)
    normalized = normalize(report_rows, config)
    write_outputs(args.out, report_rows, normalized)
    print(f"\nWrote {args.out}/engagement_report.csv and active/associate/affiliate.psv ({gz.calls} API calls)")
    if problems and not args.allow_gaps:
        print(f"\nNOT READY TO SCORE: {', '.join(problems)} came back empty, which would understate every score. "
              "Fix the mapping in growthzone_config.json (run `discover`), or rerun with --allow-gaps.")
        sys.exit(2)


def read_export(path):
    if path.lower().endswith((".xlsx", ".xlsm")):
        try:
            import openpyxl
        except ImportError:
            sys.exit("Reading .xlsx needs openpyxl (pip install openpyxl), or save the export as .csv.")
        ws = openpyxl.load_workbook(path, read_only=True, data_only=True).active
        rows = [["" if c is None else c for c in r] for r in ws.iter_rows(values_only=True)]
    else:
        with open(path, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
    header_at = next(i for i, r in enumerate(rows) if r and str(r[0]).strip() == "Contact Name")
    header = [str(h).strip() for h in rows[header_at]]
    return [dict(zip(header, r)) for r in rows[header_at + 1:]]


def cmd_from_export(config, args):
    report_rows = []
    for path in filter(None, [args.active, args.associate, args.affiliate]):
        report_rows.extend(read_export(path))
    normalized = normalize(report_rows, config)
    write_outputs(args.out, None, normalized)
    dropped = len(report_rows) - sum(len(v) for v in normalized.values())
    print(f"Wrote {args.out}: " + ", ".join(f"{t} {len(normalized[t])}" for t in TYPES)
          + f" (dropped {dropped} footer or non-member lines)")


def main():
    parser = argparse.ArgumentParser(description="Pull GBCA member engagement data from GrowthZone.")
    parser.add_argument("--config", default=os.path.join(HERE, "growthzone_config.json"))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check")
    d = sub.add_parser("discover")
    d.add_argument("--out", default=os.path.join(HERE, "data", "discovery"))
    d.add_argument("--samples", type=int, default=5, help="member records to sample")
    p = sub.add_parser("pull")
    p.add_argument("--out", default=os.path.join(HERE, "data", dt.date.today().isoformat()))
    p.add_argument("--allow-gaps", action="store_true", help="write outputs even if a scored field is empty")
    e = sub.add_parser("from-export")
    e.add_argument("--active")
    e.add_argument("--associate")
    e.add_argument("--affiliate")
    e.add_argument("--out", default=os.path.join(HERE, "data", dt.date.today().isoformat()))
    args = parser.parse_args()
    config = load_config(args.config)
    commands = {"check": cmd_check, "discover": cmd_discover, "pull": cmd_pull, "from-export": cmd_from_export}
    try:
        commands[args.command](config, args)
    except GrowthZoneError as e:
        sys.exit(f"GrowthZone: {e}")


if __name__ == "__main__":
    main()
