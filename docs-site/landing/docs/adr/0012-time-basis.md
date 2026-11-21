# 0012. Time basis

- Status: Accepted
- Date: 2026-11-19
- Deciders: Utku Can Ozturk

## Context

[ADR 0011](0011-operational-hours.md) applies the hour window to local time. The clock that produces that local time has to be the facility, because a device clock and an IP time zone follow the handset or the ISP.

## Decision

Derive local time from `created_timestamp` (backend `created_at`, UTC), converted at the facility. Resolve the zone from the official pin, then the detected coordinates, then the country's first listed zone, then UTC. Do not use the device clock. Do not use `client_info.Timezone`. Keep the first-listed-zone fallback as it is. It is defensive.

Treat `created_at` as the backend write time, in UTC, and as the timestamp closest to the test. Treat `scheduled_at` as the time the test request was sent. The device may be off then. It is not the test time.

Leave ping cadence at 15 minutes. A row that waited in the offline queue carries its sync or write time, so `local_hour` and the local date can be wrong. From app 2.0.4, `offline_synced` is meant to flag those rows. On earlier rows the flag is not a reliable test of queueing. What to do about the queued rows is [ADR 0015](0015-test-timestamp-offline-synced-rows.md).

## Consequences

`sql/fetch_spatial_confidence_ledger.sql` stores `created_at` as `created_timestamp` and does not convert it. The loader does. `sql/fetch_measurements.sql` converts with `default.country_timezones` (`COALESCE` of that table, a country-name match, then UTC). That is not the pin cascade above.

## Alternatives considered

Using `client_info.Timezone` was the old rule. IP zones follow ISP hubs and VPNs, so it is obsolete.

## Open questions

The research window, 08:00–19:59 facility-local, differs from an 8am–4pm window in the analytics tables. That is a communication question, not a code change. The analytics window is not described in this repository.

## Evidence

- `src/utils/timezone_enricher.py`: `_resolve_single_school_tz` checks `govt_latitude` / `govt_longitude`, then `detected_latitude` / `detected_longitude`, then `pytz.country_timezones` index 0, then `"UTC"`. `enrich_telemetry_with_local_time` parses `created_timestamp` into `created_timestamp_utc` and converts that. It does not read a device clock or `client_info`.
- `tests/test_spatial_foundations.py`: `test_enrichment_keeps_tz_name_and_converts_each_timezone`.
- External, not verifiable in this repo (app engineering team, 2026-11-19): `created_at` is the closest write time; `scheduled_at` is only the request time; cadence is 15 minutes on Windows 2.0.4, the Chrome extension, and Android; `offline_synced` is the 2.0.4 queue flag. Whether earlier rows store null or a default false is unverified. The app's own ping schedule is not in this repo.
