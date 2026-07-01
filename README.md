# IDMC Deep Impact Analysis

A Python tool that scans an **Informatica Intelligent Data Management Cloud (IDMC / IICS)** project and performs **object-level impact analysis** — it tells you exactly which assets (taskflows, mappings, tasks, mapplets, etc.) reference a given list of tables, columns, or keywords, and *where inside each asset* the reference occurs.

Given a set of search terms (e.g. table names like `CMC_CLCL_CLAIM` or column names like `CSCI_EMAIL`), the tool exports every asset in a project, cracks open each export package, and reports the matching component down to the individual step / transformation / property level.

## Why

When a source table or column is being changed, retired, or migrated, you need to know **every downstream IDMC object impacted**. The IDMC UI search is shallow and asset-level only. This tool goes deeper — it parses the actual exported asset definitions (taskflow XML, mapping JSON/bin, MTT task JSON) so you can see the specific **DataTask, Expression, Decision, transformation, or property** that references your term.

## Features

- **SSO cookie capture** — launches Microsoft Edge, you log in via SSO, and the tool captures the session cookies automatically (no manual token copying required).
- **Session reuse** — caches the session in `idmc_session.json`; you can also paste cookies manually.
- **Full-project export** — pages through the IDMC v3 REST API for all configured asset types, filtered to a project/location.
- **Batched export + download** — exports assets in batches, polls the export job, and downloads the ZIP packages.
- **Deep content extraction** — recursively unzips nested export packages and extracts every readable asset definition into a DataFrame.
- **Component-level parsing**:
  - **Taskflow XML** — multi-pass parser attributes each match to its owning component (DataTask, Notification, Expression, Decision/Condition, Assignment, ErrorHandler, Input Parameters, Temp Fields, etc.).
  - **Mapping (bin / JSON)** — parses the mapping structure and reports the matching property / transformation / object.
  - **MTT tasks (JSON)** — reports the matching task-config section.
  - **Everything else** — line-level matches.
- **Content caching** — pickles the extracted content (`idmc_content_cache.pkl`) so you can re-run searches instantly without re-exporting.
- **Multi-format reports** — CSV, JSON, a human-readable summary `.txt`, and a rich console report (by term, by asset type, component detail, matched-line samples, and a "not found" list).

## Requirements

- **Python 3.9+**
- **Microsoft Edge** + **msedgedriver** (matching your Edge version) on `PATH` — only needed for the automated SSO login. If you provide cookies manually, the browser step is skipped.
- Python packages:

```bash
pip install -r requirements.txt
```

`requirements.txt`:

```
requests
pandas
selenium
```

## Configuration

All configuration lives at the top of `deep_scan_upg_v3.py`:

| Setting | Description |
|---|---|
| `SEARCH_TERMS` | Dictionary of `category -> [terms]`. Add the tables/columns/keywords you want to trace. |
| `SCAN_LOCATION` | Project / location to scan (e.g. `"NYHP"`). Only assets whose path starts with this are kept. |
| `SCAN_ASSET_TYPES` | List of IDMC asset types to export (TASKFLOW, DTEMPLATE, MTT, MAPPLET, PROCESS, etc.). |
| `EXPORT_BATCH_SIZE` | Number of assets per export job (default `50`). |
| `EXPORT_TIMEOUT` | Max seconds to wait for an export job (default `120`). |
| `PAGE_SIZE` | API pagination size (default `200`). |

## Usage

### 1. First run (SSO login)

```bash
python deep_scan_upg_v3.py
```

On first run there is no session file, so the tool launches Edge. Complete your SSO login in the browser window. Once you land in the IDMC UI, the tool captures the cookies, saves them to `idmc_session.json`, validates the session, exports the project, and runs the search.

### 2. Manual cookie entry (optional)

If browser automation isn't available, run once to generate a sample `idmc_session.json`, then fill in the values from your browser:

1. Log in to IDMC via SSO in Edge/Chrome.
2. Open **F12 → Network** tab → click any request → **Cookies**.
3. Copy the values into `idmc_session.json`:

```json
{
  "IDMC_SERVER_URL": "https://use6.dm-us.informaticacloud.com",
  "IDS_TOKEN": "…",
  "USER_SESSION": "…",
  "JSESSIONID": "…",
  "X_INFA_ORG_ID": "…",
  "XSRF_TOKEN": "…"
}
```

At minimum you need either `IDS_TOKEN` or `USER_SESSION`.

### 3. Re-running searches (use the cache)

After a successful export the extracted content is cached in `idmc_content_cache.pkl`. On the next run you'll be asked whether to reuse it — this skips the API export entirely and searches in seconds.

```bash
# Force a fresh export, ignore the cache
python deep_scan_upg_v3.py --no-cache

# Only use the cache; error out if none exists (never hits the API)
python deep_scan_upg_v3.py --cache-only
```

## Command-line options

| Flag | Description |
|---|---|
| `--no-cache` | Ignore cached content and force a fresh export from IDMC. |
| `--cache-only` | Search cached data only; do not call the API (fails if no cache). |

## Output files

| File | Description |
|---|---|
| `idmc_deep_scan_report.csv` | Flat table: term, category, asset, asset type, component type/name, hit count, matched lines. |
| `idmc_deep_scan_report.json` | Same results in JSON (records orientation). |
| `idmc_deep_scan_summary.txt` | Human-readable summary grouped by search term, plus a "not found" list. |
| `idmc_session.json` | Saved session cookies (**contains secrets — git-ignored**). |
| `idmc_content_cache.pkl` | Pickled extracted content cache (**git-ignored**). |

## How it works

```
SSO login (Edge)  ─┐
manual cookies    ─┴─►  validate session (v3 REST API)
                            │
                            ▼
                     find_assets()      page through /objects per asset type, filter to SCAN_LOCATION
                            │
                            ▼
                     export_batch()     POST /export → poll job → download ZIP package
                            │
                            ▼
                 extract_zip_to_rows()  recursively unzip, decode each asset definition → DataFrame
                            │
                            ▼
                   search_content()     per-term regex match; route to the right parser:
                                          • Taskflow XML  → parse_taskflow_xml() component ownership
                                          • Mapping bin/JSON → property/transformation
                                          • MTT JSON      → task-config section
                                          • other         → line-level
                            │
                            ▼
                    write_reports()      CSV + JSON + summary.txt + console report
```

## Security notes

- `idmc_session.json` contains live session tokens. It is **git-ignored** — never commit it.
- The script disables SSL verification (`SSL_VERIFY = False`) for corporate proxy environments; set it to `True` if your environment has a valid cert chain.
- The content cache may contain sensitive asset definitions; it is git-ignored by default.

## Notes

- The tool is read-only against IDMC — it only exports assets, it never modifies anything.
- `includeDependencies` is set to `False` on export to keep packages small and scoped to the asset itself.
- Adjust `SCAN_ASSET_TYPES` if your org uses asset types not listed, or to narrow the scan for speed.
