# Research Log

This page records how the spatial methodology changed between versions and why. The methodology pages ([Blueprint](technical_blueprint.md), the three pillar pages, and [Parameters](parameters.md)) always describe the current version on their own; this log is the place for history.

Concrete facilities that motivated a change are described, anonymised, in [Worked Examples](../spatial/examples.md).

## v0.3

**Status:** frozen after replay validation (see [Validation](#validation)).

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
| `INSUFFICIENT_EVIDENCE` device class for devices with fewer than `device_min_samples` fix events or fix events on a single day | The first replay of the new rules put 44 devices in `HIGH_MOBILITY`, against 20 in v0.2. 35 of them had one day with one or two fix events and no movement at all. They could not form a supported cluster, so they fell through to the "no supported cluster" rule. The class scores like `HIGH_MOBILITY`, so no facility output changed |
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

All fixed in v0.3:

*   `TelemetryLoader` lost `tz_name` under pandas 3, because `groupby(...).apply` no longer returns the grouping column. The time zone is now mapped per facility.
*   The SQL app-version filter compared strings, so `2.0.10` sorted below `2.0.2`. Versions are now compared as integer arrays.
*   `resolution_strategy_used` reported the requested strategy even after a fallback. It is replaced by `anchor_resolved_by` and `strategy_fallback_reason`.
*   The operational-hours filter was applied to the score but not to the centroid. The anchor window now applies operational hours and workdays to the centroid and the score. Mobility uses all hours on purpose (Blueprint Section 4.1).

### Validation

v0.2 and v0.3 were replayed on the same ledger with `scripts/replay_versions.py`. The v0.2 side is the last v0.2 commit, `66d9596`. The ledger is the one behind the findings above: one country, June to mid-August 2026, 9,189 rows, 245 devices, 165 facilities, 541 BSSIDs, official pins from Delta Sharing.

**Track 1 flags:**

| Flag | v0.2 | v0.3 |
| --- | --- | --- |
| `VERIFIED_ACCURATE` | 47 | 61 |
| `CAMPUS_DISPERSION` | 11 | 7 |
| `GOVT_PIN_MISMATCH` | 76 | 80 |
| `MINOR_DISCREPANCY` | 25 | retired |
| `AMBIGUOUS_MULTI_CLUSTER` | — | 5 |
| `UNSTABLE_MOBILE_ONLY` | 0 | 1 |
| `INSUFFICIENT_DATA` | 6 | 11 |

**Flag transitions** (rows are v0.2, columns are v0.3):

| v0.2 \ v0.3 | `VERIFIED_ACCURATE` | `CAMPUS_DISPERSION` | `GOVT_PIN_MISMATCH` | `AMBIGUOUS_MULTI_CLUSTER` | `UNSTABLE_MOBILE_ONLY` | `INSUFFICIENT_DATA` |
| --- | --- | --- | --- | --- | --- | --- |
| `VERIFIED_ACCURATE` | 45 | 1 | 0 | 0 | 0 | 1 |
| `CAMPUS_DISPERSION` | 4 | 5 | 1 | 1 | 0 | 0 |
| `GOVT_PIN_MISMATCH` | 2 | 1 | 70 | 2 | 1 | 0 |
| `MINOR_DISCREPANCY` | 10 | 0 | 9 | 2 | 0 | 4 |
| `INSUFFICIENT_DATA` | 0 | 0 | 0 | 0 | 0 | 6 |

126 of 165 facilities keep their flag. The median change in distance to the pin is 0 m, and 12 facilities move by more than 1 km. The 25 retired `MINOR_DISCREPANCY` facilities now get a distance band: 9 of them are mismatches of more than 500 m that v0.2 had shown under its mildest flag.

**Confidence and actions:** 129 facilities are `HIGH`, 24 `MEDIUM` and 12 `LOW`. Recommended actions are `FIELD_VERIFY` for 84, `NONE` for 61, `AWAIT_DATA` for 13 and `SUBMIT_CORRECTION` for 7. 70 of the 80 mismatches are seen by a single device, which cannot show whether the pin or the installation is wrong, so they go to field verification.

**Device classes:**

| v0.2 \ v0.3 | `STATIONARY` | `COMMUTER` | `RELOCATED` | `HIGH_MOBILITY` | `INSUFFICIENT_EVIDENCE` | v0.2 total |
| --- | --- | --- | --- | --- | --- | --- |
| `STATIONARY` | 144 | 0 | 0 | 0 | 33 | 177 |
| `COMMUTER` | 1 | 34 | 2 | 2 | 0 | 39 |
| `RELOCATED` | 2 | 0 | 7 | 0 | 0 | 9 |
| `HIGH_MOBILITY` | 5 | 5 | 1 | 1 | 8 | 20 |
| v0.3 total | 152 | 39 | 10 | 3 | 41 | 245 |

The 33 devices v0.2 called `STATIONARY` had too little data to be called anything: v0.2 passed them because one or two readings trivially sit inside the geofence. Only 3 devices remain `HIGH_MOBILITY`.

**Hotspot and BSSID mobility:** 1,504 of the 9,189 rows are carried fixes. Excluding them from the BSSID mobility test takes the number of mobile BSSIDs from 55 to 7: 49 lose the tag and 1 gains it. Hotspot-tagged rows fall from 2,599 to 693, and hotspot-tagged BSSIDs from 204 to 132; the remaining tags come mostly from hotspot network names.

**Worked examples:** The three [Worked Examples](../spatial/examples.md) were replayed. Their v0.2 outputs match the earlier analysis exactly, and their v0.3 outputs match the design, with one difference: Example B was expected to have its confidence limited by its 130 m accuracy, but other factors put it in the `HIGH` tier. Its action is still `FIELD_VERIFY`.

**Second extract and other countries:** A later extract of the same country (8,395 rows, 186 devices, 162 facilities) gives the same picture: 118 of 162 facilities keep their flag, `HIGH_MOBILITY` falls from 13 to 3 devices, and hotspot-tagged rows fall from 2,430 to 385. Ledgers from three more countries (about 1,700 facilities in total) were run through v0.3 alone. Every facility in all four ledgers satisfies the Track 1 distance bands, the support and anchor rules, the confidence tiers and the `SUBMIT_CORRECTION` conditions. Two random facilities per flag and country were also reviewed by hand.

### Findings Recorded for Later Versions

*   **Country-wide pin offset.** In one country, 410 of 805 facilities are `CAMPUS_DISPERSION`. The anchors sit a median of about 226 m from their pins, mostly in the same direction: the median facility pin is about 211 m west and 29 m south of its anchor. Removing that shared shift leaves a median residual of 64 m. The other three countries show no shared shift, with medians under 5 m. This points to a registry-wide error such as a datum or projection problem, not to dispersed campuses. v0.3 reports it facility by facility (Blueprint Section 9); a registry-level check is a candidate for a later version.
*   **Missing device identifiers.** In one country about three quarters of rows have no `device_id`, from older app versions. These rows still support facility clusters but cannot be classified by device, so `distinct_devices` can be 0 for a supported facility.

## v0.2

Introduced the **Two-Track Engine**. Earlier iterations used a single-flag cascade in which a hardware anomaly, for example a laptop carried 200 km, replaced the location answer even when the main cluster matched the government pin. v0.2 split the output into Track 1 (location truth, from the unpenalized score S\_raw) and Track 2 (hardware integrity, S\_raw x P\_coherence), added the BSSID Coherence Penalty, the consumer-hotspot regex, and the BSSID drift check, and introduced configurable cluster-resolution strategies.

## Before v0.2

Single-flag cascade: one output flag per facility combined location and hardware outcomes.
