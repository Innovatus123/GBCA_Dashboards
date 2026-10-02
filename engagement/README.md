# Member engagement: GrowthZone pull and scoring

Two scripts:

- `growthzone.py` pulls member engagement data from GBCA's GrowthZone tenant, or reads a GrowthZone report export.
- `score_engagement.py` scores each member against the 2026 Active, Associate and Affiliate scorecards.

Member data never goes in this repository, because the repository is public. Everything under `engagement/data/` and `engagement/reports/` is git-ignored.

## One-time setup: the GrowthZone API key

1. A GrowthZone admin creates a key at **Settings > Advanced Settings > API Key Permissions**. Give it read access to contacts, memberships, groups, custom fields, events and purchases/invoices. It does not need write access.
2. Store the key as an environment variable named `GROWTHZONE_API_KEY`:
   - **Claude Code cloud sessions:** open the environment menu in the session title bar, choose Edit, and add `GROWTHZONE_API_KEY`. New sessions pick it up.
   - **Windows:** `setx GROWTHZONE_API_KEY "<key>"`, then open a new terminal.
3. Never commit the key or paste it into chat.

The tenant URL is set in `growthzone_config.json` (`generalbuildingcontractorsassociationagc.growthzoneapp.com`). The key is sent as `Authorization: ApiKey <key>`. `GROWTHZONE_ACCESS_TOKEN` (OAuth bearer) and `GROWTHZONE_BASE_URL` are optional alternatives.

## First live run

```
python growthzone.py check                      # key works; member counts by type
python growthzone.py discover                   # raw samples -> data/discovery/, lists custom-field names
python growthzone.py pull --out data/<date>     # builds the 17-column report + scorer inputs
python score_engagement.py --data data/<date> --json data/<date>/scores.json
python build_report.py --scores data/<date>/scores.json --compare data/<earlier>/scores.json \
    --as-of "<date>" --window "<window>" --out reports/GBCA_Member_Engagement_Report_<date>.html
```

`discover` shows the custom-field names and activity descriptions GrowthZone actually returns. Check them against `growthzone_config.json` before relying on `pull`. These parts of the config are the ones most likely to need adjusting:

| Report field | Where `pull` gets it |
|---|---|
| Member, type, tenure | `/api/memberships/all` (types carry a dollar-volume tier, matched by word) and the membership summary on the organization record |
| Spotlights, awards, tuition, issue resolution, content, meeting space, vendor, special programs | Organization custom fields (`/api/contacts/{id}/NotesAndFields`), year multi-selects |
| Committee participation, bargaining rights | "Committee Participation" and "Bargaining Rights" category lists on the organization record |
| Active individuals | Related contacts on the organization record (`TotalRecordAvailable`) |
| Event attendees | Quantities on "Event Registration" line items in the window (GrowthZone counts registrants) |
| Membership and non-dues spend | Every purchase in the window (`/api/purchase`, then `/api/thirdparty/purchase/{id}`), credited to the member billed or the member a paying individual belongs to; "Membership Dues" line items are dues, everything else is non-dues |

The window defaults to the trailing 12 months, the saved GrowthZone report's window; `--window-start`/`--window-end` override it. Purchase details are cached in `data/cache/` so reruns are fast.

`pull` prints a reconciliation against the Aug 4, 2026 export (member counts, event totals and spend totals by type) and field coverage. It exits without scoring if any scored field comes back empty, because an empty field silently understates every score. The comparison baseline (Aug 4, 2026 totals by type) lives in the git-ignored `data/baseline.json`, since spend totals should not be public. Set both date windows to match the saved GrowthZone report before comparing totals.

## Writing scores back to GrowthZone

The API is read-only (GBCA's published spec has no endpoint that creates a field or writes a value), so scores go back through GrowthZone's own import:

1. One time, a GrowthZone admin creates two Organization custom fields at **Settings > Custom Fields > Add**: `Engagement Score` (Text) and `Engagement Risk Level` (Dropdown: Highly Engaged, Engaged, Low Risk, Moderate Risk, High Risk). Other names go in `import_fields` in `growthzone_config.json`.
2. Build the import file:
   ```
   python growthzone.py import-file --scores data/<date>/scores.json
   ```
   It looks up each member's account number through the API. Without a key, pass a GrowthZone contacts export that has Account Number and Organization Name columns: `--accounts contacts.csv`. Members with no account number are listed in a separate `_no_account_number.csv`, and the command stops if two members share an account number.
3. In GrowthZone, run **Contacts > Import** with the file and map the two score columns to the custom fields. Import updates a contact whose Account Number matches instead of creating a new one.

Once imported, the fields can be added as columns and filters in any GrowthZone contact report.

## Weekly refresh (cloud routine)

A Claude Code cloud routine runs `weekly.py` every Saturday at 11:15 PM Eastern:

```
python weekly.py --prev <last week's GBCA_Member_Engagement_Scores_<date>.json> --prev-date <date> [--key-file <key file>]
```

`weekly.py` pulls live GrowthZone data for the trailing 365 days, scores it, and stops before building anything if the pull is incomplete, fewer than 300 members come back, or the count fell more than 10% from last week. Otherwise it writes, under `reports/weekly/`:

- `GBCA_Member_Engagement_Report.html`, compared with last week (who moved into or out of risk, who joined or left)
- `GBCA_Member_Engagement_Scores_<date>.json`, next week's comparison file, with member spend removed
- `summary.json`, the figures for the run report
- `GBCA_Member_Engagement_Report_New.html` and `GBCA_Member_Engagement_Scores_New_<date>.json`, the same week under scoring model v2 (`--prev-new` takes last week's file)

The routine then moves each destination's current `GBCA_Member_Engagement_Report.html` into its `Archived` folder as `GBCA_Member_Engagement_Report_<previous date>.html` and uploads the new one, and does the same for `GBCA_Member_Engagement_Report_New.html` (archived as `GBCA_Member_Engagement_Report_New_<previous date>.html`). Both scores files go to Box `Archived/Data` as next week's comparison files. The key comes from `GROWTHZONE_API_KEY` when it is set; otherwise `--key-file` reads it from a text file, and the key is never printed. Dates follow Eastern time, because 11:15 PM Saturday is already Sunday in UTC.

## Scoring model v2 (go-forward model)

`GBCA_Member_Engagement_Report_New.html` scores members with separate scorecards for Active, Associate and Affiliate members, trained on ten years of GrowthZone renewals. The original report (`GBCA_Member_Engagement_Report.html`, 2026 scorecards) is still produced each week for comparison.

| File | Role |
|---|---|
| `model_v2.py` | Inputs, scorecards, scoring (stdlib only). `python model_v2.py --data data/<date> --json data/<date>/scores_v2.json` |
| `scoring_model_v2.json` | Points, weights and calibration for each member type |
| `model_validation_v2.json` | Aggregate validation results shown in the report |
| `train_model_v2.py` | Rebuilds the history cache (`fetch`) and retrains (`train`); needs numpy and scikit-learn |
| `build_report_v2.py` | Builds the new report |

Each member gets a 0-100 score, a calibrated chance of leaving within 12 months, and a band: **At Risk** (15%+), **Watch** (7-15%), **Stable** (3-7%), **Secure** (under 3%). Inputs, all observable in GrowthZone on the scoring date: tenure, non-dues spend in the last 12 months, time since the last event or purchase, dues payment timing, and for Active and Associate members the size tier in the membership type name and bargaining rights. `growthzone.py pull` writes them to `features_v2.csv`.

How it was built: every member on Oct 1 of 2016-2025 was described with data dated on or before that day and labeled by whether it was still a member a year later (3,003 member-years, 227 departures). GrowthZone billing detail starts in 2019, so activity inputs are learned from the 2020 cohort on, with "unknown" indicators for earlier years. Affiliates have their own model; Active and Associate share one with separate size tiers and an Active adjustment, because Active members had too few departures to fit alone. Validation uses years each model never saw (leave-one-year-out, and train 2016-2022 / test 2023-2025).

Committee seats are deliberately not scored. GrowthZone keeps only current rosters, so members who stayed show seats they took after the scoring date and members who left show none; that look-ahead made committee participation look far more protective than the most recent year supports.

Retrain each fall once the new year's outcomes are in: `python train_model_v2.py fetch` then `python train_model_v2.py train`, and check the printed accuracy against the previous `model_validation_v2.json` before committing.

## Without the API: a GrowthZone report export

Export the "GBCA Member Engagement Report" for each member type (.csv, or .xlsx with `pip install openpyxl`), then:

```
python growthzone.py from-export --active active.csv --associate associate.csv --affiliate affiliate.csv --out data/<date>
python score_engagement.py --data data/<date>
```

This drops GrowthZone's footer lines ("Count\Average\Totals", "Generated ... by ..."). In the Sep 28, 2026 chart those lines were counted as four members.
