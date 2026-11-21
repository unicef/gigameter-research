# 0009. SQL conventions

- Status: Proposed
- Date: 2026-11-18
- Deciders: Utku Can Ozturk

## Context

Track C queries are not in the repo yet. Three conventions need one place before the first of those queries. This ADR stays Proposed: the bandwidth and retransmission wording is not in the SQL, and the legacy-client coalesce is not validated.

## Decision

Do not treat this ADR as implemented. Apply it with the first Track C query.

1. Compare app versions as integer arrays, not as strings. This part is already in the ledger, coverage, and country queries.
2. Report NDT7 BBR bandwidth as `BBRInfo.BW` in bytes/s × 8 / 1e6, in Mbps. Define retransmission ratio as `BytesRetrans / BytesSent`, and extract both fields. Do not call that ratio packet loss. This wording was set on 2026-11-18. The SQL does not do it yet.
3. Queries that span app 2.x and older clients must coalesce the nested NDT7 paths with the flat NDT-5 keys. This part is unvalidated. Current NDT extraction reads only the nested NDT7 paths.

## Consequences

[Traceroutes & BBR](../diagnostics/routing.md) calls `BBRInfo.BW` bytes/sec and does not apply × 8. That page is frozen methodology, so this ADR does not edit it. The two statements disagree until a freeze adopts one.

## Evidence

- `sql/fetch_spatial_confidence_ledger.sql` compares `app_version` with integer arrays. The same predicate is in `fetch_spatial_confidence_ledger_all.sql`, `fetch_spatial_telemetry_coverage.sql`, and `fetch_countries_with_coordinates.sql`.
- [Research Log](../blueprint/research-log.md), "Code Defects Found in v0.2": a string comparison sorted `2.0.10` below `2.0.2`.
- `sql/fetch_measurements.sql` and `sql/fetch_measurements_utc.sql` store `$["NDTResult.S2C"].LastServerMeasurement.BBRInfo.BW` as a raw double, `bbr_bottleneck_bw`, and `TCPInfo.TotalRetrans` as `tcp_total_retrans`. They do not select `BytesRetrans` or `BytesSent`, and they do not read flat NDT-5 keys.
- `sql/fetch_measurements.sql` has no `app_version` filter. Whether a future Track C query excludes older clients before the coalesce is still open.
