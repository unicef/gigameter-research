# 0011. Operational hours are applied from SpatialConfig

- Status: Accepted
- Date: 2026-11-19
- Deciders: Utku Can Ozturk

## Context

Local time is `created_timestamp` converted at the facility. That conversion does not decide which hours count.

## Decision

Apply the window from `SpatialConfig`.

`SpatialConfig.operational_hours` is an inclusive pair of integer local hours, and the end hour covers HH:00–HH:59. `in_operational_hours` is the only comparison. A fix event keeps the flag from its first row, so a burst that starts inside the window and finishes outside it stays in the anchor window. Governance percentages, the hourly chart, and the BSSID split count every row and do not apply the workday filter. An overnight window is rejected.

`(8, 19)` means 08:00:00–19:59:59. The anchor requires both `is_workday` and `is_operational_hours`. The profiler recomputes the flag per row from `local_hour` only. The enricher does not write the flag. `methodology_version` stays `"0.3"`.

## Open questions

Which timestamp is the real test time for a row synced after the device was offline is unresolved. See [ADR 0015](0015-test-timestamp-offline-synced-rows.md).

## Evidence

- `src/spatial_intelligence/config.py`: default `(8, 19)`; `__post_init__` requires integers 0–23, rejects bools, requires start ≤ end, and rejects an overnight window; `in_operational_hours` is the comparison.
- `src/spatial_intelligence/fix_events.py`: `mark_fix_events` recomputes the flag and logs one warning when an incoming stamp disagrees; `build_fix_event_table` takes `is_operational_hours` with `"first"`.
- `src/spatial_intelligence/spatial_profiler.py`: `_apply_operational_hours`; `_anchor_window_events` requires `is_workday` and `is_operational_hours`. Governance and BSSID counts sum the recomputed flag across rows.
- `tabs/tab_01_governance.py`: the hourly chart groups every row by `local_hour` and `is_operational_hours`.
- `src/utils/timezone_enricher.py` does not write `is_operational_hours`.
- `tests/test_spatial_foundations.py`: `test_recomputed_operational_hours_replace_a_disagreeing_stamp`, `test_burst_crossing_the_end_hour_stays_in_window_from_its_first_row`, `test_operational_hour_window_is_not_hard_coded_outside_config` (the hard-coded `BETWEEN 8 AND 19` form is rejected outside config), `test_measurement_sql_does_not_stamp_operational_hours`.
- `tests/test_spatial_profiler.py`: `test_anchor_window_requires_workday_and_operational_hours_flags`.
- [Research Log](/gigameter-research/geofencing/latest/blueprint/research-log/), "Operational-hours wiring".
