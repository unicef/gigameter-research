# Research Log

This page records how the spatial methodology changed between versions and why. The methodology pages ([Blueprint](technical_blueprint.md), the three pillar pages, and [Parameters](parameters.md)) always describe the current version on their own; this log is the place for history.

Concrete facilities that motivated a change are described, anonymised, in [Worked Examples](../spatial/examples.md).

## v0.3 (draft)

**Status:** design approved; code in progress.

### Findings That Motivated v0.3

Replaying v0.2 on one country ledger (summer 2026, about 9,200 rows from 245 devices) showed:

*   **Repeated coordinates are the norm.** 72% of rows carry exactly the same `(lat, lon, accuracy)` as the previous row from the same device. The median gap between such repeats is about 4 hours 40 minutes, and 19% repeat after more than a day.
*   **Coordinates can be carried across networks.** 66% of changes in associated BSSID keep the previous row's exact coordinates. In one case a home network carried the school's coordinates from about 12 hours earlier, 3 km away.
*   **Cluster labels were treated as meaningful.** DBSCAN cluster `0` (the first cluster in time) was used as the primary cluster.
*   **Rows without a BSSID were averaged across locations.** When that group had the most scans, every row for the facility was averaged, placing the facility between real locations.
*   **The Track 1 cascade had a gap.** Any score from 50 to below 70 produced `MINOR_DISCREPANCY`, including offsets of 15–38 km.
*   **Mobility depended on the facility centroid.** A wrong centroid made every device fail the geofence and fall into `HIGH_MOBILITY`.

### Method Changes

| Change | Reason |
| --- | --- |
| Fix events replace rows as the evidence unit | Repeated and carried coordinates inflated density and made fixed routers look mobile |
| Device mobility runs before facility selection and does not use the facility centroid | A wrong centroid misclassified every device; it also made `STATIONARY_FIRST` impossible |
| Facility anchor is one observation cluster; no averaging across clusters | Averages across locations produced points where no device had been |
| Two strategies always run, with agreement and a registry-name tie-break | Strategy fallback was silent and the reported strategy was the requested one |
| A cluster name-matches only when the facility's SSID is seen there on at least `min_support_device_days` device-days | In the commuter example a single non-carried reading of the school SSID sat in the home cluster, so both candidates matched and the tie-break could not decide |
| Track 1 flag is set by distance; confidence is a separate tier with a recommended action | Low and medium scores hid large offsets |
| Track 2 split measured between supported clusters | Stray readings and the no-BSSID group produced false splits |
| Track 3 (entity attribution) added | No way to tell a wrong pin from telemetry recorded somewhere else |
| All settings in one versioned config | Constants were duplicated, and some existed only in the docs |

### Retired

| Item | Replacement |
| --- | --- |
| `MINOR_DISCREPANCY` flag | Distance band plus `location_confidence_level` |
| Geofence compliance &ge; 90% for `STATIONARY` | One supported cluster with noise share &le; `max_noise_share` |
| BSSID daily-mean drift > 1000 m | DBSCAN-based `is_mobile_bssid` test |
| BSSID merge at 200 m (documented, never implemented) | `anchor_eps_m` |
| Single strategy selection | Strategy pair with agreement |

### Parameter Changes

| Parameter | v0.2 | v0.3 |
| --- | --- | --- |
| `device_min_samples` | 3 rows | 3 fix events |
| `min_support_device_days` (`INSUFFICIENT_DATA`) | 5 rows | 2 device-days |
| `stationary_min_compliance_pct` | 90 | removed |
| `bssid_drift_m` | 1000 (daily means) | removed |
| `workdays` | not applied | Mon–Fri |
| Track 1 confidence gates | 70 (verified, mismatch), 60 (campus), 50 (unstable) | tiers at 70 and 50, independent of distance |
| `hotspot_share_min` | 50% of rows | 50% of non-carried fix events |

### Code Defects Found in v0.2

To be fixed during the v0.3 implementation:

*   `TelemetryLoader` loses `tz_name` under pandas 3, because `groupby(...).apply` no longer returns the grouping column.
*   The SQL app-version filter compares strings, so `2.0.10` sorts below `2.0.2`.
*   `resolution_strategy_used` reports the requested strategy even after a fallback.
*   The operational-hours filter is applied to the score but not to the centroid or to mobility.

## v0.2

Introduced the **Two-Track Engine**. Earlier iterations used a single-flag cascade in which a hardware anomaly, for example a laptop carried 200 km, replaced the location answer even when the main cluster matched the government pin. v0.2 split the output into Track 1 (location truth, from the unpenalized score S\_raw) and Track 2 (hardware integrity, S\_raw x P\_coherence), added the BSSID Coherence Penalty, the consumer-hotspot regex, and the BSSID drift check, and introduced configurable cluster-resolution strategies.

## Before v0.2

Single-flag cascade: one output flag per facility combined location and hardware outcomes.
