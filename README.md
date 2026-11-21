# GigaMeter Research

Research code for [GigaMeter](https://github.com/unicef/project-connect-daily-check-app) (the Daily Check App), UNICEF Giga's application that monitors internet connectivity in schools, health facilities, and refugee camps. The repository turns GigaMeter telemetry into evidence about where facilities are, how their monitoring devices behave, and how well they are connected.

**Documentation:** [unicef.github.io/gigameter-research](https://unicef.github.io/gigameter-research/latest/) holds the methodology, the research log, and the Python API reference. It is the source of truth for how every result is computed.

**Current version:** v0.3 of the spatial methodology.

## Research Areas

| Area | Status |
| --- | --- |
| Spatial geofencing and location validation | Implemented (v0.3) |
| Outages and connectivity | Research in progress |
| Network diagnostics and routing | Research in progress |

### Spatial geofencing (v0.3)

Each GigaMeter speedtest carries a Wi-Fi geolocation result. The spatial methodology uses these readings to answer three questions per facility:

1. **Location truth:** Where is the facility, and how far is it from the official government pin? Each facility gets a distance flag, a confidence tier, and a recommended action such as `FIELD_VERIFY` or `SUBMIT_CORRECTION`.
2. **Hardware integrity:** Are the monitoring devices fixed installations, or laptops and hotspots that move?
3. **Entity attribution:** Is the telemetry plausibly from the registered facility, rather than a neighbour or a staff member's home?

The three answers are reported separately and never merged into one flag. The method is described in the [Blueprint](https://unicef.github.io/gigameter-research/latest/blueprint/technical_blueprint/), its settings on the [Parameters](https://unicef.github.io/gigameter-research/latest/blueprint/parameters/) page, and its validation in the [Research Log](https://unicef.github.io/gigameter-research/latest/blueprint/research-log/).

## Repository Layout

| Path | Contents |
| --- | --- |
| `src/spatial_intelligence/` | The spatial methodology: configuration, fix events, device mobility, facility anchors, and scoring |
| `src/utils/` | Telemetry loading and local-time enrichment |
| `sql/` | Queries that export telemetry ledgers from the GigaMeter database |
| `app.py`, `tabs/` | Streamlit research dashboard |
| `scripts/` | Research tools, such as replaying two methodology versions on one ledger |
| `tests/` | Test suite |
| `docs/` | Documentation source (MkDocs) |

## Installation

Python 3.10 or newer is required.

```bash
git clone git@github.com:unicef/gigameter-research.git
cd gigameter-research
pip install -e ".[dashboard,docs,dev]"
```

The extras are optional: `dashboard` adds Streamlit, `docs` adds MkDocs and `mike`, and `dev` adds pytest. Code is imported from the repository root, for example `from src.spatial_intelligence.facility_validator import FacilityValidator`.

## Configuration

Analyses on exported ledger files need no credentials. Credentials are only needed to query the database or to load official pins, and are read from a `.env` file in the repository root. Never commit it. The two `GIGAMETER_*` settings are ordinary environment variables read by the dashboard.

| Variable | Needed for |
| --- | --- |
| `DB_CONFIG` | Running the SQL templates in `sql/` (`query_name=...`) |
| `API_PROFILE_FILE_PATH`, `API_SHARE_NAME`, `API_SCHEMA_NAME` | Loading official facility pins from Delta Sharing (`country_iso3=...`) |
| `GIGAMETER_LEDGER_DIR` | Dashboard ledger folder (default `data/spatial_confidence_ledger`) |
| `GIGAMETER_LIVE_PINS` | Set to `0` to start the dashboard with the pins stored in the ledger |

## Quick Start

```python
from src.spatial_intelligence.facility_validator import FacilityValidator

validator = FacilityValidator(file_path="data/spatial_confidence_ledger/XXX/XXX_ledger.csv")
audit = validator.run_national_facility_audit()   # one row per facility
audit["location_verification_flag"].value_counts()
```

A ledger is an export of `sql/fetch_spatial_confidence_ledger.sql` for one country. Telemetry can also be passed as a DataFrame or fetched with a SQL template. The [API overview](https://unicef.github.io/gigameter-research/latest/api/) explains the inputs, the processing order, and how to change settings, and the output columns are listed in [Blueprint Section 7](https://unicef.github.io/gigameter-research/latest/blueprint/technical_blueprint/#7-output-schema).

## Research Dashboard

```bash
streamlit run app.py
```

The dashboard reads one ledger per country from `data/spatial_confidence_ledger/{ISO3}/` and has four tabs: ledger governance, national audit, facility inspector, and device mobility. It is built to inspect research results, not to act on them, so it has no export or correction features.

## Data Handling

Ledgers and audit outputs contain facility and device identifiers.

* `data/`, CSV, and Parquet files are gitignored. Keep ledgers and analysis outputs out of the repository.
* Facility locations come only from the Wi-Fi geolocation result (`detected_latitude`, `detected_longitude`). The coarse IP location in `client_info` is never used as a facility position.

## Development

```bash
pytest                              # test suite
scripts/docs.sh build-all           # strict build of every site into site/
scripts/docs.sh serve-landing       # preview one site (also serve-geofencing, serve-outage, serve-routing)
```

A test fails when a public class or function is missing from the API reference, so new code needs a docstring and an entry in `docs/api/` (a symlink to `docs-site/geofencing/docs/api/`).

**Versioning.** The landing site is unversioned. Geofencing is published per minor version with `mike` under its own prefix. Outage and routing stay unversioned drafts until their first release. Every `mike` command includes `--deploy-prefix`. There must never be a `versions.json` at the site root. Do not use `mkdocs gh-deploy`; it would replace `gh-pages` and wipe the geofencing tree.

Publish from the docs branch. Each command below commits on local `gh-pages` and prints the push. Push once, after the last commit. A rehearsal sets `DOCS_PAGES_BRANCH` to another local branch and skips the push.

```bash
scripts/docs.sh migrate-gh-pages

mike deploy -F docs-site/geofencing/mkdocs.yml --deploy-prefix geofencing --update-aliases --title "v0.3" v0.3 latest
mike set-default -F docs-site/geofencing/mkdocs.yml --deploy-prefix geofencing latest

scripts/docs.sh publish landing
scripts/docs.sh publish outage
scripts/docs.sh publish routing
scripts/docs.sh publish redirects

git push origin gh-pages
```

`migrate-gh-pages` runs once. It moves `v0.2/` to `geofencing/v0.2/`, removes the root `v0.3/`, `latest/`, and `versions.json`, writes the legacy redirect stubs, and puts the landing build at the root. It keeps the v0.2 entry in `geofencing/versions.json` so the next `mike deploy` can add v0.3 without dropping v0.2. Later releases use `publish` for the landing site, outage, routing, and the redirect stubs. `publish` commits only when that site's files changed, so landing and the redirect stubs are unchanged on the first run after migrate. Geofencing versions stay on the `mike` commands above. `set-default` runs under `geofencing/`, so the site root stays the landing page.

Track-prefixed tags (`geofencing-vX.Y.Z`, `outage-vX.Y.Z`, `routing-vX.Y.Z`) apply from the next release. Tags `v0.3.0`, `v0.3.1`, and `v0.3.2` stay as they are. `pyproject.toml` remains the package version.

Links inside one site stay relative, so they remain on that version. Links that cross sites are root-absolute, for example `/gigameter-research/adr/0011-operational-hours/` and `/gigameter-research/geofencing/latest/blueprint/research-log/`. `scripts/redirect_legacy_docs.py` writes refresh stubs for the old `/v0.2/`, `/v0.3/`, and `/latest/` URLs. Methodology changes and their reasons are recorded in the [Research Log](https://unicef.github.io/gigameter-research/geofencing/latest/blueprint/research-log/).

## License

Licensed under the [GNU Affero General Public License v3.0](LICENSE).
