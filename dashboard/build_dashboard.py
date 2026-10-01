"""Build the GBCA Dashboard from the latest GBCA Member Engagement Report (run by the Sunday cloud routine).

  python build_dashboard.py --report GBCA_Member_Engagement_Report.html \
      --history data/engagement_history.json [--as-of 2026-10-04] [--out out]

Reads the five-band counts that engagement/build_report.py embeds in the report (VALIDATED) and the
report's as-of date, adds them to the weekly history, and writes under --out:

  GBCA Dashboard.html                              one self-contained file (the Box copy)
  onedrive/GBCA Dashboard.html                     the OneDrive shell, which loads the folder below
  onedrive/GBCA Dashboard files/                   style.css, live-data.js, sample-data.js, app-1..4.js
  onedrive/GBCA Dashboard files/manifest.json      bytes and sha256 of each OneDrive file
  engagement_history.json                          the history with this report added
  summary.json                                     figures for the run report

Only live-data.js changes from week to week, so the OneDrive refresh is one small upload; the manifest
shows when a code change means other files must go up too.

--report can be repeated to backfill older reports (the Archived copies) into the history. Exits
non-zero, before writing anything, if a report cannot be read, has fewer than min_members, or the
member count fell more than max_drop from the previous week in the history.
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")
KEYS = ("he", "en", "lo", "mo", "hi")          # Highly Engaged, Engaged, Low Risk, Moderate Risk, High Risk
NAME = "GBCA Dashboard"
FILES_DIR = f"{NAME} files"
APP_PARTS = ("app_core.js", "app_charts.js", "app_live.js", "app_sections.js")


def fail(message):
    print(f"\nDASHBOARD BUILD STOPPED: {message}")
    sys.exit(1)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def js_json(value):
    """JSON safe to place inside a <script> element."""
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")


def parse_report(path, classes):
    """As-of date and five-band counts per class from a GBCA_Member_Engagement_Report.html."""
    text = read(path)
    found = re.search(r"const VALIDATED = (\{.*?\});\s*$", text, re.M)
    when = re.search(r"Live GrowthZone data as of ([A-Z][a-z]{2} \d{1,2}, \d{4})", text)
    if not found or not when:
        fail(f"{os.path.basename(path)} is not a GBCA Member Engagement Report built by build_report.py "
             "(no VALIDATED counts or as-of date).")
    counts = json.loads(found.group(1))
    date = dt.datetime.strptime(when.group(1), "%b %d, %Y").date()
    out = {}
    for c in classes:
        row = counts.get(c)
        if not isinstance(row, dict) or any(not isinstance(row.get(k), int) or row[k] < 0 for k in KEYS):
            fail(f"{os.path.basename(path)}: counts for {c} are missing or malformed.")
        out[c] = [row[k] for k in KEYS]
    every = counts.get("All members")
    if every and [every.get(k) for k in KEYS] != [sum(out[c][j] for c in classes) for j in range(5)]:
        fail(f"{os.path.basename(path)}: the All members row does not equal the sum of the classes.")
    return {"date": date.isoformat(), "c": out}


def week_key(date):
    y, w, _ = date.isocalendar()
    return f"{y}-W{w:02d}"


def total(snapshot):
    return sum(sum(v) for v in snapshot["c"].values())


def rollup(levels):
    he, en, lo, mo, hi = levels
    n = he + en + lo + mo + hi
    return {"members": n, "engaged": he + en, "low_risk": lo, "risk": mo + hi,
            "engaged_pct": round(100 * (he + en) / n, 1) if n else None,
            "risk_pct": round(100 * (mo + hi) / n, 1) if n else None}


def compact_sample(sample, classes):
    """The layout sample in a compact form: the issue log becomes rows of day numbers and list indexes,
    which app_core.js expands again. Deterministic, so the file only changes when the sample does."""
    issues = dict(sample["issues"])
    log = issues.pop("log")
    epoch = dt.date(1970, 1, 1)
    owners = sorted({x["own"] for x in log})
    bases = sorted({x["basis"] for x in log})
    rows = []
    for k, x in enumerate(log):
        if x["id"] != f"ISS-26-{k + 1:04d}" or not re.fullmatch(r"M-\d+", x["mem"]):
            fail(f"sample issue {x['id']} does not follow the ISS-26-NNNN / M-NNNN pattern the compact form relies on.")
        o = (dt.date.fromisoformat(x["o"]) - epoch).days
        r = (dt.date.fromisoformat(x["r"]) - epoch).days - o if x.get("r") else -1
        rows.append([o, r, classes.index(x["cls"]), int(x["mem"][2:]), issues["categories"].index(x["cat"]),
                     owners.index(x["own"]), x["cost"], bases.index(x["basis"])])
    issues.update(owners=owners, bases=bases, log=rows)
    return dict(sample, issues=issues)


def main():
    parser = argparse.ArgumentParser(description="Build the GBCA Dashboard from the latest engagement report.")
    parser.add_argument("--report", action="append", required=True,
                        help="GBCA_Member_Engagement_Report.html; repeat to backfill older reports")
    parser.add_argument("--history", help="engagement_history.json from last week (optional the first time)")
    parser.add_argument("--as-of", help="build date, YYYY-MM-DD (default: today, Eastern)")
    parser.add_argument("--config", default=os.path.join(HERE, "dashboard_config.json"))
    parser.add_argument("--out", default=os.path.join(HERE, "out"))
    args = parser.parse_args()

    cfg = json.loads(read(args.config))
    classes = cfg["classes"]
    as_of = dt.date.fromisoformat(args.as_of) if args.as_of else dt.datetime.now(ZoneInfo(cfg["timezone"])).date()

    history = {"version": 1, "weeks": {}}
    if args.history and os.path.exists(args.history):
        history = json.loads(read(args.history))
    weeks = history["weeks"]
    reports = sorted((parse_report(p, classes) for p in args.report), key=lambda s: s["date"])
    latest = reports[-1]
    if dt.date.fromisoformat(latest["date"]) > as_of:
        fail(f"the report is dated {latest['date']}, after the build date {as_of}.")
    for snap in reports:
        n = total(snap)
        if n < cfg["min_members"]:
            fail(f"the report of {snap['date']} has {n} members (expected at least {cfg['min_members']}).")
        key = week_key(dt.date.fromisoformat(snap["date"]))
        have = weeks.get(key)
        if not have or have["date"] <= snap["date"]:
            weeks[key] = snap

    # Same guard as engagement/weekly.py: a sharp week-over-week fall means a bad pull, not lost members.
    ordered = sorted(weeks.values(), key=lambda s: s["date"])
    at = next(k for k, s in enumerate(ordered) if s["date"] == latest["date"])
    prior = ordered[at - 1] if at else None
    if prior and total(latest) < total(prior) * (1 - cfg["max_drop"]):
        fail(f"{total(latest)} members on {latest['date']}, down from {total(prior)} on {prior['date']} "
             f"(more than {cfg['max_drop']:.0%}).")
    stale = (as_of - dt.date.fromisoformat(latest["date"])).days > cfg["stale_days"]

    # The calendar: the last weeks_shown ISO weeks, ending with the week of the build date.
    monday = as_of - dt.timedelta(days=as_of.weekday())
    cal = []
    for k in range(cfg["weeks_shown"] - 1, -1, -1):
        start = monday - dt.timedelta(weeks=k)
        cal.append({"wk": start.isocalendar()[1], "start": start.isoformat(),
                    "end": (start + dt.timedelta(days=6)).isoformat()})
    eng = [weeks.get(week_key(dt.date.fromisoformat(w["start"]))) for w in cal]
    shown = [s for s in ordered if s["date"] <= as_of.isoformat()]
    live = {
        "built": as_of.isoformat(),
        "classes": classes,
        "weeks": cal,
        "eng": eng,
        "latest": {"date": shown[-1]["date"]} if shown else None,
        "links": cfg["links"],
        "syncRoot": cfg["sync_root"],
        "targets": {k: v for k, v in cfg["targets"].items() if not k.startswith("_")},
        "riskAlert": cfg["risk_alert_share"],
    }

    sample = json.loads(read(os.path.join(SRC, "sample_data.json")))
    if len(sample["weeks"]) != cfg["weeks_shown"]:
        fail(f"the sample has {len(sample['weeks'])} weeks; weeks_shown is {cfg['weeks_shown']}.")
    files = {
        "style.css": read(os.path.join(SRC, "style.css")),
        "live-data.js": f"window.GBCA_LIVE = {js_json(live)};\n",
        "sample-data.js": f"window.GBCA_SAMPLE = {js_json(compact_sample(sample, classes))};\n",
    }
    for k, part in enumerate(APP_PARTS, 1):
        files[f"app-{k}.js"] = read(os.path.join(SRC, part))
    scripts = ["live-data.js", "sample-data.js"] + [f"app-{k}.js" for k in range(1, len(APP_PARTS) + 1)]

    page = read(os.path.join(SRC, "index.html")).replace("<!--LOGO-->", read(os.path.join(SRC, "logo.svg")).strip())
    single = (page.replace("<!--STYLE-->", f"<style>\n{files['style.css']}</style>")
              .replace("<!--SCRIPTS-->", "\n".join(f"<script>\n{files[s]}</script>" for s in scripts)))
    href = FILES_DIR.replace(" ", "%20")
    shell = (page.replace("<!--STYLE-->", f'<link rel="stylesheet" href="{href}/style.css">')
             .replace("<!--SCRIPTS-->", "\n".join(f'<script src="{href}/{s}"></script>' for s in scripts)))

    limit = cfg["max_bundle_file_bytes"]
    bundle = {f"{NAME}.html": shell, **{f"{FILES_DIR}/{k}": v for k, v in files.items()}}
    manifest = {}
    for rel, text in bundle.items():
        data = text.encode("utf-8")
        if len(data) > limit:
            fail(f"{rel} is {len(data)} bytes; OneDrive files stay under {limit} so the connector upload is reliable. "
                 "Split it in dashboard/src.")
        manifest[rel] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

    out = args.out
    write(os.path.join(out, f"{NAME}.html"), single)
    for rel, text in bundle.items():
        write(os.path.join(out, "onedrive", rel), text)
    write(os.path.join(out, "onedrive", FILES_DIR, "manifest.json"), json.dumps(manifest, indent=2) + "\n")
    write(os.path.join(out, "engagement_history.json"), json.dumps(history, indent=1) + "\n")

    def by_class(snap):
        if not snap:
            return None
        return {**{c: rollup(snap["c"][c]) for c in classes},
                "All members": rollup([sum(snap["c"][c][j] for c in classes) for j in range(5)])}

    summary = {
        "as_of": as_of.isoformat(),
        "week": week_key(as_of),
        "report_date": latest["date"],
        "stale": stale,
        "live_weeks_in_view": sum(1 for s in eng if s),
        "this_week": by_class(eng[-1]),
        "previous": {"date": prior["date"], **by_class(prior)} if prior else None,
        "single_file": {"path": os.path.join(out, f"{NAME}.html"), "bytes": len(single.encode("utf-8"))},
        "onedrive": manifest,
    }
    write(os.path.join(out, "summary.json"), json.dumps(summary, indent=2) + "\n")

    now = summary["this_week"]
    print(f"Built {NAME} for {week_key(as_of)} (as of {as_of}); engagement report of {latest['date']}"
          + (" - STALE" if stale else ""))
    if now:
        a = now["All members"]
        print(f"Members {a['members']}: engaged {a['engaged']} ({a['engaged_pct']}%), low risk {a['low_risk']}, "
              f"risk {a['risk']} ({a['risk_pct']}%)")
    print(f"Single file {summary['single_file']['bytes']} bytes; OneDrive bundle "
          + ", ".join(f"{os.path.basename(k)} {v['bytes']}" for k, v in manifest.items()))


if __name__ == "__main__":
    main()
