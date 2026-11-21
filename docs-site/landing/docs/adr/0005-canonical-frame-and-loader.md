# 0005. One loader, one canonical frame

- Status: Accepted
- Date: 2026-11-19
- Deciders: Utku Can Ozturk

## Context

Later stages were renaming columns and joining the schools table again. Two passes could disagree about the same facility.

## Decision

Give `TelemetryLoader.load` exactly one source. Build `db` and `delta_store` from `.env` only when that source needs them. Canonicalise columns once, in the loader, and do not fall back to legacy telemetry names after that. Have `FacilityValidator` build fix events, device classes, and anchors once and pass them down. Do not alias identifiers or re-merge schools inside analyzers.

The column contract is [ADR 0013](0013-canonical-frame-contract.md). Pin ownership is [ADR 0014](0014-pin-ownership.md).

## Evidence

- `src/utils/data_loader.py`: `load`, `_read_source` (exactly one of frame, file, or query), `_checked_db_connection`, `_delta_store_or_default`, `canonicalize_telemetry_columns`.
- `tests/test_telemetry_loader.py`: `test_rejects_zero_or_two_sources`, `test_canonicalize_renames_aliases_once`, `test_facility_validator_reuses_spatial_summary`.
- `src/spatial_intelligence/facility_validator.py` builds one `SpatialProfiler` and passes its `fix_event_rows` into `MobilityAnalyzer`.
- `prepare_schools_frame` still accepts `giga_id_school` on a schools table. Analyzer modules do not rename telemetry identifiers.
