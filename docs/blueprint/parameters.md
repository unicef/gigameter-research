# Methodology Parameters

**Version:** <span style="background-color: #677eff; color: white; padding: 3px 12px; border-radius: 8px; font-size: 0.9em; font-weight: 500; display: inline-block;">v0.3 draft</span>

All spatial settings live in one frozen `SpatialConfig` passed to `MobilityAnalyzer`, `SpatialProfiler`, and `FacilityValidator`. Every output row carries `methodology_version` and a hash of the config, so results can be reproduced and compared across settings.

**Columns:**

*   **Value:** the current default.
*   **Since:** the methodology version in which the setting took its current value.
*   **Status:** `in use` for settings carried over from an earlier version, `proposed` for starting points that still need calibration.

Earlier values and the reasons they changed are in the [Research Log](research-log.md).

The config checks ordering constraints when it is created, for example `verified_max_m < mismatch_min_m`, `coherence_full_m < split_m`, and `device_min_samples >= 2`.

## Evidence & Time Window

| Parameter | Value | Since | Status | Used by |
| --- | --- | --- | --- | --- |
| `operational_hours` | 08:00–19:59 local | 0.2 | in use | Anchor window, score |
| `workdays` | Mon–Fri | 0.3 | proposed | Anchor window |
| `burst_window_s` | 300 | 0.3 | proposed | Fix events |
| `accuracy_floor_m` | 1.0 | 0.2 | in use, calibrate | Centroid weights |
| `min_support_device_days` | 2 | 0.3 | proposed | Supported facility clusters, registry name match, `INSUFFICIENT_DATA` |

## Hotspot & BSSID Mobility

| Parameter | Value | Since | Status | Used by |
| --- | --- | --- | --- | --- |
| `hotspot_ssid_pattern` | consumer hotspot regex | 0.2 | in use | `is_hotspot_ssid` |
| `bssid_mobility_accuracy_gate_m` | 200 | 0.3 | proposed | `is_mobile_bssid` |
| `bssid_mobility_eps_m` | 250 | 0.3 | proposed | `is_mobile_bssid` |
| `bssid_mobility_min_samples` | 2 | 0.3 | proposed | `is_mobile_bssid` |
| `bssid_mobility_min_cluster_days` | 2 | 0.3 | proposed | `is_mobile_bssid` |

## Device Mobility (Pillar 1)

| Parameter | Value | Since | Status | Used by |
| --- | --- | --- | --- | --- |
| `device_eps_m` | 150 | 0.2 | in use | Device DBSCAN |
| `device_min_samples` | 3 fix events | 0.3 | proposed | Device DBSCAN |
| `min_cluster_device_days` | 2 | 0.3 | proposed | Supported clusters |
| `max_noise_share` | 0.25 | 0.3 | proposed | `STATIONARY` |
| `commuter_min_alternations` | 2 | 0.3 | proposed | `COMMUTER` |
| `geofence_radius_m` | 200 | 0.2 | in use | Compliance audit after anchor selection |

## Facility Anchor (Pillar 2)

| Parameter | Value | Since | Status | Used by |
| --- | --- | --- | --- | --- |
| `anchor_eps_m` | 150 | 0.3 | proposed | Facility DBSCAN |
| `govt_anchor_radius_m` | 2000 | 0.2 | in use | `GOVT_PROXIMITY_ANCHOR` |
| `strategies` | `GOVT_PROXIMITY_ANCHOR`, `TELEMETRY_DOMINANCE` | 0.3 | proposed | Agreement check |
| `name_match_generic_tokens` | per-language list | 0.3 | proposed | Registry name match |

## Raw Score (S\_raw)

| Parameter | Value | Since | Status |
| --- | --- | --- | --- |
| Weights (stability, consensus, bssid, depth, precision) | 30, 25, 20, 15, 10 | 0.2 | in use |
| Stability points (stationary, commuter, other) | 30, 20, 10 | 0.2 | in use |
| Consensus full / zero | &le; 30 m / > 200 m; single device 12.5 | 0.2 | in use |
| BSSID full points | non-hotspot BSSID on &ge; 3 days | 0.2 | in use |
| Depth full points | 10 device-days | 0.3 | in use (unit changed) |
| Precision full / zero | &le; 10 m / &ge; 100 m | 0.2 | in use |

## Track 1: Location Truth

| Parameter | Value | Since | Status |
| --- | --- | --- | --- |
| `verified_max_m` | 200 | 0.2 | in use |
| `mismatch_min_m` | 500 | 0.2 | in use |
| Confidence `HIGH` | S\_raw &ge; 70 | 0.3 | proposed |
| Confidence `MEDIUM` | 50 &le; S\_raw < 70 | 0.3 | proposed |
| Confidence `LOW` | S\_raw < 50 | 0.3 | proposed |

## Track 2: Hardware Integrity

| Parameter | Value | Since | Status |
| --- | --- | --- | --- |
| `coherence_full_m` | 1000 | 0.2 | in use |
| `split_m` | 2000 | 0.2 | in use |
| `coherence_floor` | 0.1 | 0.2 | in use |
| `hotspot_share_min` | 50% of non-carried fix events | 0.3 | in use (unit changed); also excludes hotspot clusters from anchor candidates |

## Track 3: Entity Attribution

| Parameter | Value | Since | Status |
| --- | --- | --- | --- |
| `other_entity_radius_m` | 200 | 0.3 | proposed |
