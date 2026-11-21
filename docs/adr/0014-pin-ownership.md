# 0014. Pin ownership

- Status: Accepted
- Date: 2026-11-19
- Deciders: Utku Can Ozturk

## Context

Official pins can arrive on an enriched frame, on a caller-supplied schools table, or from Delta Sharing. The loader has to pick one source. The dashboard also loads a second table for Track 3. See [ADR 0006](0006-official-pins-delta-sharing.md).

## Decision

`TelemetryLoader` owns pins. The class has to work for any caller, and a ledger is a frozen input.

On a frame whose local time is already complete, accept the govt pins already on it and do not call Delta. Non-null `govt_latitude` / `govt_longitude` are the usual case, for example an enriched ledger. If `schools_df` is also passed, only cross-check, by haversine distance. Raise `ValueError` when a pin is more than `PIN_MATCH_M` (1 m) away, or when the frame pin is null and `schools_df` has a coordinate for that facility. Do not treat these as mismatches: a facility missing from one side, extra rows, a null coordinate in `schools_df`, or both sides null.

On a frame that still needs local time, take pins from `schools_df`, then from non-null govt columns, then from Delta via the country code. All-null govt columns count as missing. If none of those sources exist, raise.

## Open questions

The app ingest workflow is not settled.

`app.py` `load_live_pins` pulls live Delta Sharing pins, on unless `GIGAMETER_LIVE_PINS=0`, and passes them only as Track 3 `entity_pins`. Tracks 1 and 2 keep the ledger pins. One dashboard run can mix two pin versions.

Fix that by redesigning the app's ingest workflow, not by patching the toggle. One example, not a decision: refresh pins at ingest through the loader and record the Delta snapshot date.

## Evidence

- `src/utils/data_loader.py`: `_clock_is_complete` chooses the enriched branch; `_reject_pin_mismatch` and `_differing_facility_count` implement the 1 m and null-frame rules; `_merge_school_pins` is the non-enriched order; `PIN_MATCH_M = 1.0`. The enriched branch keys off a complete clock, including a frame whose govt pins are null, and still does not call Delta unless `schools_df` is passed.
- `tests/test_telemetry_loader.py`: `test_enriched_frame_is_reused_with_or_without_a_country_code`, `test_enriched_matching_schools_df_keeps_frame_pins`, `test_enriched_schools_df_mismatch_raises`, `test_enriched_null_frame_pin_against_schools_df_raises`, `test_enriched_subset_schools_df_leaves_other_pins`, `test_schools_df_merge_does_not_call_delta`, `test_existing_govt_pins_skip_delta_on_query_path`, `test_all_null_govt_columns_with_country_code_load_delta`, `test_missing_pin_source_raises`.
- `app.py`: `LIVE_PINS_DEFAULT` and `load_live_pins`; `build_engine` passes those pins only as `entity_pins`. `src/spatial_intelligence/facility_validator.py` uses `entity_pins` for Track 3 and leaves the telemetry govt columns on the frame used for Tracks 1 and 2.
