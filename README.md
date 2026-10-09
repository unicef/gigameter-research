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

validator = FacilityValidator(file_path="data/spatial_confidence_ledger/ALB/ALB_ledger.csv")
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
mkdocs serve                        # preview the documentation
mkdocs build --strict               # check the documentation before a release
```

A test fails when a public class or function is missing from the API reference, so new code needs a docstring and an entry in `docs/api/`.

**Versioning.** Methodology releases are tagged `vX.Y.Z` on `main`. The documentation is published per minor version with `mike`, for example `mike deploy --push --update-aliases v0.3 latest`, and earlier versions stay available from the version picker. Methodology changes and their reasons are recorded in the [Research Log](https://unicef.github.io/gigameter-research/latest/blueprint/research-log/).

## License

Licensed under the [GNU Affero General Public License v3.0](LICENSE).
