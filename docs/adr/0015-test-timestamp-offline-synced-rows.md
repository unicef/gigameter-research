# 0015. Test timestamp for offline-synced rows

- Status: Proposed
- Date: 2026-11-19
- Deciders: Utku Can Ozturk

## Context

[ADR 0012](0012-time-basis.md) turns `created_at` into local time. A row that sat in the offline queue carries write time, so its local hour can fall outside the window that the test actually ran in. Changing the clock is a methodology change for v0.4, not a patch. Roadmap priority P3.

## Decision

Do not adopt this yet. The candidate is:

`test_timestamp_utc = COALESCE(NDT S2C StartTime, created_at)`, plus a `test_time_source` flag.

Derive local time from `test_timestamp_utc`. Keep `created_at` as the write time.

StartTime is the M-Lab server timestamp in UTC, at `$["NDTResult.S2C"].LastServerMeasurement.ConnectionInfo.StartTime` in `results`.

## Consequences

Accept this only after replaying tag `v0.3.1` against the candidate and counting changed anchor events. Whether `created_at` itself changes when a queued row syncs is unverified.

## Evidence

- `sql/fetch_measurements.sql` does not extract `ConnectionInfo.StartTime`.
- External, not verifiable in this repo. One anonymised country, `created_at` from January through March 2026:
  - StartTime is present on about 90–97% of rows from app 1.0.9, and on none before that.
  - The lag from StartTime to `created_at` has a median of 22–24 s on every version. The 95th percentile is 28–45 s.
  - Only app 2.0.3 has a long tail: 99th percentile 2,336 s, mean 1,712 s.
  - The gain is mainly that 2.0.3 offline tail.
