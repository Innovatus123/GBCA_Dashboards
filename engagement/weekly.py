"""Weekly refresh of the GBCA Member Engagement Report (run by the Saturday cloud routine).

Pulls live GrowthZone data, scores it, checks it, and builds the report against the previous
week's scores. It only writes files under reports/weekly/; the routine archives the previous
report and uploads the new one to Box and OneDrive with its connectors.

  python weekly.py --prev prev_scores.json --prev-date 2026-10-01 [--key-file key.txt]

Writes
  reports/weekly/GBCA_Member_Engagement_Report.html
  reports/weekly/GBCA_Member_Engagement_Scores_<date>.json   next week's --prev (no spend figures)
  reports/weekly/summary.json                                 what changed, for the run report

Exits non-zero, before writing the report, if the pull is incomplete or the member count
looks wrong (under --min-members, or down more than --max-drop from the previous week).
"""

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
TZ = "America/New_York"
TYPES = ("Active", "Associate", "Affiliate")
RISK = ("Moderate Risk", "High Risk")
REPORT_NAME = "GBCA_Member_Engagement_Report.html"


def fail(message):
    print(f"\nWEEKLY RUN STOPPED: {message}")
    sys.exit(1)


def key_from_file(path):
    """The GrowthZone API key from a text file. The key itself is never printed."""
    with open(path, encoding="utf-8-sig") as f:
        lines = f.read().splitlines()
    found = [(line, t) for line in lines for t in re.findall(r"[A-Za-z0-9_\-+/=]{20,}", line)]
    tokens = list(dict.fromkeys(t for _, t in found))
    if len(tokens) > 1:
        tokens = list(dict.fromkeys(t for line, t in found if "key" in line.lower()))
    if len(tokens) != 1:
        fail(f"could not pick out a single API key in {os.path.basename(path)} "
             f"({len(tokens)} candidates). Put the key on its own line.")
    return tokens[0]


def write_archive_scores(src, dest):
    """Scores for next week's comparison, without member spend (the comparison never uses it)."""
    with open(src, encoding="utf-8") as f:
        scores = json.load(f)
    for t in TYPES:
        for m in scores["types"][t]["members"]:
            m.pop("non_spend", None)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(scores, f, separators=(",", ":"))


def members(scores):
    return [dict(m, type=t) for t in TYPES for m in scores["types"][t]["members"]]


def label(day):
    return f"{day:%b} {day.day}, {day.year}"


def run(cmd, env):
    print("\n$ " + " ".join(os.path.basename(c) if c == sys.executable else c for c in cmd), flush=True)
    result = subprocess.run(cmd, cwd=HERE, env=env)
    if result.returncode:
        fail(f"{os.path.basename(cmd[1])} exited with code {result.returncode}; see the output above.")


def main():
    parser = argparse.ArgumentParser(description="Weekly GBCA Member Engagement Report refresh.")
    parser.add_argument("--prev", help="previous week's scores JSON (GBCA_Member_Engagement_Scores_<date>.json)")
    parser.add_argument("--prev-date", help="date of the previous report, YYYY-MM-DD")
    parser.add_argument("--key-file", help="text file holding the GrowthZone API key, used when "
                                           "GROWTHZONE_API_KEY is not set")
    parser.add_argument("--out", default=os.path.join(HERE, "reports", "weekly"))
    parser.add_argument("--min-members", type=int, default=300)
    parser.add_argument("--max-drop", type=float, default=0.10, help="largest allowed week-over-week drop")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    # GrowthZone dates and tenure follow Eastern time; the cloud runs in UTC, where 11:15 PM
    # Saturday is already Sunday.
    env = dict(os.environ, TZ=TZ)
    if not (env.get("GROWTHZONE_API_KEY") or env.get("GROWTHZONE_ACCESS_TOKEN")):
        if not args.key_file:
            fail("no GrowthZone key. Set GROWTHZONE_API_KEY or pass --key-file.")
        env["GROWTHZONE_API_KEY"] = key_from_file(args.key_file)
    today = dt.datetime.now(ZoneInfo(TZ)).date()
    start = today - dt.timedelta(days=365)
    data = os.path.join(HERE, "data", today.isoformat())
    scores_path = os.path.join(data, "scores.json")

    run([sys.executable, "growthzone.py", "pull", "--out", data, "--window-start", start.isoformat(),
         "--window-end", today.isoformat(), "--workers", str(args.workers)], env)
    run([sys.executable, "score_engagement.py", "--data", data, "--json", scores_path], env)

    with open(scores_path, encoding="utf-8") as f:
        now = members(json.load(f))
    prev, prev_date = [], None
    if args.prev:
        with open(args.prev, encoding="utf-8") as f:
            prev = members(json.load(f))
        prev_date = dt.date.fromisoformat(args.prev_date) if args.prev_date else None

    total = len(now)
    if total < args.min_members:
        fail(f"only {total} members came back (expected at least {args.min_members}).")
    if prev and total < len(prev) * (1 - args.max_drop):
        fail(f"{total} members, down from {len(prev)} last week (more than {args.max_drop:.0%}).")

    os.makedirs(args.out, exist_ok=True)
    report = os.path.join(args.out, REPORT_NAME)
    build = [sys.executable, "build_report.py", "--scores", scores_path, "--as-of", label(today),
             "--window", f"{label(start)} - {label(today)}", "--out", report]
    if prev:
        since = f"{prev_date:%b} {prev_date.day}" if prev_date else "last week"
        build += ["--compare", args.prev, "--roster-compare", args.prev, "--compare-label", since,
                  "--roster-label", f"the {since} report",
                  "--compare-note", f"scores from the {since} weekly run, same method and window length."]
    run(build, env)
    write_archive_scores(scores_path, os.path.join(args.out, f"GBCA_Member_Engagement_Scores_{today.isoformat()}.json"))

    def risk_share(rows):
        return round(100 * sum(m["corrected_level"] in RISK for m in rows) / len(rows), 1) if rows else None

    before = {m["name"]: m for m in prev}
    after = {m["name"]: m for m in now}
    summary = {
        "date": today.isoformat(),
        "previous_date": prev_date.isoformat() if prev_date else None,
        "report": report,
        "report_bytes": os.path.getsize(report),
        "members": {t: sum(m["type"] == t for m in now) for t in TYPES},
        "total": total,
        "at_risk": sum(m["corrected_level"] in RISK for m in now),
        "at_risk_pct": risk_share(now),
        "previous_at_risk_pct": risk_share(prev),
        "active_at_risk": sum(m["type"] == "Active" and m["corrected_level"] in RISK for m in now),
        "joined": sorted(set(after) - set(before)) if prev else [],
        "left": sorted(set(before) - set(after)) if prev else [],
        "moved_into_risk": sorted(n for n, m in after.items() if n in before and m["corrected_level"] in RISK
                                  and before[n]["corrected_level"] not in RISK),
        "moved_out_of_risk": sorted(n for n, m in after.items() if n in before and m["corrected_level"] not in RISK
                                    and before[n]["corrected_level"] in RISK),
    }
    with open(os.path.join(args.out, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\nReport {report} ({summary['report_bytes']} bytes), as of {label(today)}")
    print(f"Members {total}: " + ", ".join(f"{t} {n}" for t, n in summary["members"].items()))
    trend = f" (last week {summary['previous_at_risk_pct']}%)" if prev else ""
    print(f"Moderate or High Risk: {summary['at_risk']} ({summary['at_risk_pct']}%){trend}; "
          f"Active at risk: {summary['active_at_risk']}")
    if prev:
        print(f"Joined {len(summary['joined'])}, left {len(summary['left'])}, moved into risk "
              f"{len(summary['moved_into_risk'])}, moved out of risk {len(summary['moved_out_of_risk'])}")


if __name__ == "__main__":
    main()
