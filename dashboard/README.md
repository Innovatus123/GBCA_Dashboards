# GBCA Dashboard

The weekly member review. The member count and section 1.0 (Member Engagement) are live: they come from the latest `GBCA_Member_Engagement_Report.html` that `engagement/weekly.py` builds every Saturday night. Sections 2.0 to 4.0 (NPS, member value, issue resolution) are still the layout sample and are tagged **Sample** wherever they appear.

Nothing built here goes in this repository, because the repository is public. `dashboard/out/` and `dashboard/data/` are git-ignored; the weekly history lives in Box.

## What the dashboard shows

- **Six measures at the top.** Member count opens the GBCA Member Map. Member engagement scrolls to section 1.0. NPS, member value, issues resolved and cost avoidance are sample.
- **Section 1.0, the roll-up view.** The report's five scorecard bands become three: **Engaged** (Highly Engaged + Engaged), **Low Risk**, and **Risk** (Moderate + High Risk). The section shows all members and each class, a 13-week chart of the three shares, and a detail table that keeps all five bands.
- **Comparisons** are against the most recent earlier week that has a live report. Weeks before the live history began show "No live report".
- **Targets** for the engaged share are `null` in `dashboard_config.json` until leadership signs off, so the pills read "No target". Set a share (for example `0.25`) per class and for `All` to turn on On track, Watch and Off track. `risk_alert_share` (0.5) adds a needs-attention item for any class with more than half its members at Risk.

## Build

```
python build_dashboard.py --report GBCA_Member_Engagement_Report.html \
    --history data/engagement_history.json --out out [--as-of YYYY-MM-DD]
```

`--as-of` defaults to today in Eastern time. The calendar is the 13 ISO weeks (Monday to Sunday) ending with that week. `--report` can be repeated to backfill archived reports into the history. The build stops, before writing anything, if:

- a report is not one `build_report.py` made, or its All members row does not add up;
- it has fewer than 300 members;
- the count fell more than 10% from the previous week in the history (the same guards as `weekly.py`);
- the report is dated after the build date.

A report more than 8 days old still builds, and the current week shows "No live report". `summary.json` flags it as `stale`.

It writes, under `--out`:

| File | Use |
|---|---|
| `GBCA Dashboard.html` | One self-contained file, about 100 KB. The Box copy; it works anywhere, including as a download. |
| `onedrive/GBCA Dashboard.html` plus `onedrive/GBCA Dashboard files/` | The OneDrive copy: a shell that loads `style.css`, `live-data.js`, `sample-data.js` and `app-1.js` to `app-4.js`. This is the same layout as the Member Map, and each file stays under 24 KB so the Microsoft 365 connector can upload it. |
| `onedrive/GBCA Dashboard files/manifest.json` | Bytes and sha256 for each OneDrive file. Week to week only `live-data.js` changes; any other file that differs from the manifest already in OneDrive needs uploading too, because the code changed. |
| `engagement_history.json` | One five-band snapshot per ISO week, the latest report in each week. Goes back to Box `GBCA Dashboard/Data`. |
| `summary.json` | Members and the roll-up by class, this week and the previous live week, for the run report. |

## Links

The Member count tile and the "Full report" button link to the components in OneDrive (`links` in `dashboard_config.json`). When the dashboard is opened from the synced `0 - GBCA SharePoint/Dashboards` folder, they use the relative paths into `Components/` (`01_Member_Map/GBCA Member Map.html`, `02_Member_Engagement/GBCA_Member_Engagement_Report.html`). Opened anywhere else, including the Box copy, they use the OneDrive web addresses.

## Weekly refresh (cloud routine)

A Claude Code cloud routine runs every Sunday at 10:48 PM Eastern, about a day after the Saturday engagement run (11:15 PM):

1. Download the current `GBCA_Member_Engagement_Report.html` from Box `20_GBCA/80_Automations/02_Member_Engagement`, and `engagement_history.json` from `GBCA Dashboard/Data`.
2. Run `build_dashboard.py`. If it exits non-zero, nothing is moved or uploaded.
3. **Box** (`20_GBCA/80_Automations/GBCA Dashboard`): copy the current `GBCA Dashboard.html` into `Archived` as `GBCA Dashboard <previous build date>.html`. Upload the new file as a new version of the same file, so its link never changes. Upload the history as a new version in `Data`.
4. **OneDrive** (`0 - GBCA SharePoint/Dashboards`): replace `GBCA Dashboard files/live-data.js` in place. Then replace any other file whose sha256 differs from the manifest in OneDrive (`sharepoint_update_file` with `expectedBytes`), and the manifest last. OneDrive version history keeps earlier copies.
5. Report the member count, the Engaged, Low Risk and Risk shares against last week, and where the files landed.
