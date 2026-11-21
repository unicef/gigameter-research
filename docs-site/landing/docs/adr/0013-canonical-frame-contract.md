# 0013. Canonical frame contract

- Status: Accepted
- Date: 2026-11-19
- Deciders: Utku Can Ozturk

## Context

[ADR 0005](0005-canonical-frame-and-loader.md) canonicalises once. "Required" was easy to misread as "non-null", which would drop older rows and unresolved Wi-Fi lookups.

## Decision

After canonicalisation, require `school_id_giga`, `device_id`, `detected_latitude`, `detected_longitude`, and `created_timestamp`. Required means the column is present. It does not mean the values are non-null.

Keep rows with a null `device_id`. The SQL always selects it, and older app versions leave it empty. Never drop those rows for the null. Keep null detected coordinates in the frame. Spatial classes drop those rows later. Do not impute them, and do not take them from IP coordinates. Leave a missing pin null.

Pass a fully enriched frame through unchanged when both `local_created_timestamp` and `local_hour` are present and neither contains nulls. Raise `ValueError` when local time is only partly present, or when either column contains nulls.

Do not make `is_operational_hours` a loader column. See [ADR 0011](0011-operational-hours.md). The column table is on the [Data Loading](/gigameter-research/geofencing/latest/api/loading/) page.

## Open questions

Rows without a `device_id` skip the device step. `MobilityAnalyzer` visits each `device_id` from `unique()`, and a null does not match any row, so those rows are not classified. The v0.4 path for them is undefined.

## Evidence

- `src/utils/data_loader.py`: `REQUIRED_TELEMETRY_COLUMNS`; `_clock_is_complete` raises on a partial clock or on nulls, and returns false when both clock columns are absent; `_require_columns` checks presence only.
- `tests/test_telemetry_loader.py`: `test_partial_or_null_local_time_raises`, `test_skips_clients_when_frame_is_already_enriched`.
- [Data Loading](/gigameter-research/geofencing/latest/api/loading/): nullable `device_id`, null detected coordinates, and no IP fill.
- [Blueprint](/gigameter-research/geofencing/latest/blueprint/technical_blueprint/), Data Dictionary Rules: missing `device_id` still counts as facility evidence and is left out of device mobility. `spatial_profiler._unique_values` drops nulls before the device-id list. `pandas.Series.nunique` does not count them.
- `src/spatial_intelligence/mobility_analyzer.py`: `analyze_device_mobility` filters with `device_id == device_id`. On pandas 2.3.3 that comparison matches no row when the id is null, and the call returns an error.
