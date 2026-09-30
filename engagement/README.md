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
```

`discover` shows the custom-field names and activity descriptions GrowthZone actually returns. Check them against `growthzone_config.json` before relying on `pull`. These parts of the config are the ones most likely to need adjusting:

| Report field | Where `pull` gets it | Confidence |
|---|---|---|
| Member, type, years as member | `/api/memberships/all` | High (documented schema) |
| Spotlights, awards, committee, tuition, issue resolution, content, meeting space, vendor, special programs, bargaining rights | Organization custom fields (`/api/contacts/{id}/NotesAndFields`), matched by the names in `custom_fields` | High once names are confirmed |
| Committee fallback | Group memberships (`/api/contacts/OrgGeneral/{id}`) | Medium |
| Active individuals | Related contacts on the organization record | Medium |
| Membership and non-dues spend | `/api/purchase`, matched by organization name, from `purchases.window_start` | Medium: verify totals |
| Event attendees | Contact activity log, matched by `events.activity_match`, from `events.window_start` | Low until verified |

`pull` prints a reconciliation against the Aug 4, 2026 export (member counts, event totals and spend totals by type) and field coverage. It exits without scoring if any scored field comes back empty, because an empty field silently understates every score. The comparison baseline (Aug 4, 2026 totals by type) lives in the git-ignored `data/baseline.json`, since spend totals should not be public. Set both date windows to match the saved GrowthZone report before comparing totals.

## Without the API: a GrowthZone report export

Export the "GBCA Member Engagement Report" for each member type (.csv, or .xlsx with `pip install openpyxl`), then:

```
python growthzone.py from-export --active active.csv --associate associate.csv --affiliate affiliate.csv --out data/<date>
python score_engagement.py --data data/<date>
```

This drops GrowthZone's footer lines ("Count\Average\Totals", "Generated ... by ..."). In the Sep 28, 2026 chart those lines were counted as four members.
