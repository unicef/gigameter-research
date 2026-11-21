# 0006. Official pins come from Delta Sharing

- Status: Accepted
- Date: 2026-11-18
- Deciders: Utku Can Ozturk

## Context

Location truth needs one official pin source. An earlier note asked for one live snapshot per run for every track.

## Decision

Load official pins from Delta Sharing. The loader calls `delta_store.load_table` with the country code and renames that table's `latitude` and `longitude` to `govt_latitude` and `govt_longitude`. Who supplies pins at run time is [ADR 0014](0014-pin-ownership.md).

## Consequences

The "one live snapshot per run for all tracks" idea was narrowed on 2026-11-19. [ADR 0014](0014-pin-ownership.md) leaves the app ingest workflow open, so one dashboard run can still mix two pin versions.

The name `school_master` is not in this repository. `giga-spatial` 0.11.1's `load_table` takes whatever table name the caller passes, and this repo passes the country code. Share and schema come from `API_SHARE_NAME` and `API_SCHEMA_NAME`.

## Evidence

- `src/utils/data_loader.py`: `prepare_schools_frame`; `_merge_school_pins` calls `store.load_table(country_iso3)`.
- `tests/test_telemetry_loader.py`: `test_delta_load_when_schools_df_omitted`.
- `README.md`, Configuration: Delta Sharing credentials and the share and schema variables.
- `gigaspatial/core/io/delta_sharing_data_store.py` in `giga-spatial` 0.11.1: `load_table(table_name)`.
