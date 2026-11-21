# 0010. Python and dependencies

- Status: Accepted
- Date: 2026-11-19
- Deciders: Utku Can Ozturk

## Context

The spatial code has to run on the interpreters that are actually tested. Pandas 3 changed `groupby`, and a loader bug showed up only there.

## Decision

Support Python ≥ 3.10 and pandas 2.3 and 3.0. Run the tests on both. Take shared distance helpers from `giga-spatial`. Other helpers in `src/spatial_intelligence/geo.py` may move there.

## Open questions

One test is unaccounted for between Python 3.10 (115 passed) and Python 3.14 (113 passed, 1 skipped). That count is external and was not investigated here. No CI workflow in this repo runs the matrix.

## Evidence

- `pyproject.toml`: `requires-python = ">=3.10"`, `pandas>=2.3,<4`, `giga-spatial>=0.9.8`.
- `README.md`: Python 3.10 or newer.
- `src/spatial_intelligence/geo.py`: `haversine_m` calls `gigaspatial.processing.calculate_distance`. Weighted centroids and the DBSCAN wrapper still live in that module.
- [Research Log](/gigameter-research/geofencing/latest/blueprint/research-log/): `TelemetryLoader` lost `tz_name` under pandas 3; the time zone is now mapped per facility.
- No `.github` workflow is in the repository.
