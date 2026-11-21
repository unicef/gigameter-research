# Worked Examples: Hard-to-Call Facilities

These examples show where a version of the methodology struggled and how the next version responds. They are illustrations, not rules. Each output is labelled with the methodology version that produced it, and the outputs will change as the method changes.

Identifiers, network names, MAC addresses, and coordinates are removed. Distances are rounded. The method changes these examples led to are summarised in the [Research Log](../blueprint/research-log.md).

!!! note "How these outputs were produced"
    Both columns are measured: each version's code was replayed on the same country ledger (summer 2026, about 9,200 rows from 245 devices).

## Example A: One Fixed Router, Short Window

**Telemetry:** One device, one associated router, 7 rows over 3 days. Six rows sit within a few metres of each other. The first reading after start-up lands about 400 m away.

**Registry:** The official pin is about 15 km from the cluster.

| | v0.2 | v0.3 |
| --- | --- | --- |
| Device class | `HIGH_MOBILITY` (6/7 rows inside the geofence, below 90%) | `STATIONARY` (one supported cluster, one noise event) |
| Track 1 | `MINOR_DISCREPANCY`, score 53.7 | `GOVT_PIN_MISMATCH`, score 62.7, `MEDIUM`, `FIELD_VERIFY` |
| Track 2 | no tags | no tags |
| Track 3 | — | `UNRESOLVED` (network name does not reference the facility) |

**Why it is hard:** The device is clearly stationary, but a single device on a residential-style network cannot show whether it sits in the facility or somewhere else. The pin may be wrong, or the device may be installed elsewhere.

## Example B: Mostly Wired, One Off-Site Day

**Telemetry:** One device over seven weeks. About two thirds of rows have no associated Wi-Fi (wired or unassociated). The remainder use a network whose name matches the registered facility name. On one day the device appears about 90 km away on a residential network.

**Registry:** The official pin is about 17 km from the main cluster.

| | v0.2 | v0.3 |
| --- | --- | --- |
| Facility centroid | Average of all rows, dragged toward the off-site day; about 38 km from the pin | Main cluster only; about 17 km from the pin |
| Device class | `HIGH_MOBILITY` (0% compliance against the dragged centroid) | `STATIONARY` (off-site day is unsupported noise) |
| Track 1 | `MINOR_DISCREPANCY`, score 57.5 | `GOVT_PIN_MISMATCH`, score 77.5, `HIGH`, `FIELD_VERIFY` |
| Track 2 | `BSSID_SPATIAL_SPLIT` | no split (only one supported cluster) |
| Track 3 | — | `CONSISTENT` (network name matches the registry name) |

**Why it is hard:** The first reading suggests the device is at a different facility. The network name instead points to a registry pin that is far off. v0.2 hid a 38 km offset under its mildest flag.

Mean accuracy in the cluster is about 130 m, so the precision factor scores 0. Fifteen days from one stationary device still put the anchor in the `HIGH` tier. The action stays `FIELD_VERIFY` because a correction needs at least two devices.

## Example C: Commuter Laptop Over a School Holiday

**Telemetry:** One laptop over ten weeks. On school days early in the window it connects to a network named after the facility, about 300 m from the official pin. It also uses two home networks about 3 km away. After the term ends it stays at home. In many rows the coordinates are copied from the previous row even though the associated network changed.

| | v0.2 | v0.3 |
| --- | --- | --- |
| Hotspot tagging | 100% of rows tagged, because carried coordinates made both fixed routers look as if they moved | About 2% of fix events tagged, the genuine phone-hotspot events |
| Facility centroid | Facility network's rows mixed both locations; centroid about 1.9 km from the pin | Govt proximity picks the facility cluster (about 300 m from the pin); telemetry dominance picks the home cluster (about 3.4 km) |
| Device class | `COMMUTER` | `COMMUTER` |
| Track 1 | `GOVT_PIN_MISMATCH`, score 75.8 | Strategies disagree; the registry name match picks the facility cluster: `CAMPUS_DISPERSION` (about 300 m), score 69.3, `MEDIUM`, `FIELD_VERIFY`, `anchor_resolved_by = ssid_name_match` |
| Track 2 | `HOTSPOT_TETHERED_FACILITY` | `BSSID_SPATIAL_SPLIT` (home and facility clusters are both supported, about 3.2 km apart), `COMMUTER_DEVICE` |
| Track 3 | — | `CONSISTENT` |

**Why it is hard:** By volume, the home is the dominant location because the window spans a holiday. Without the name match the honest answer is `AMBIGUOUS_MULTI_CLUSTER`. A term calendar is not modelled in v0.3.
