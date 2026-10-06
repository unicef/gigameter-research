# Worked Examples: Hard-to-Call Facilities

These examples show where a version of the methodology struggled and how the next version is expected to respond. They are illustrations, not rules. Each output is labelled with the methodology version that produced it, and the outputs will change as the method changes.

Identifiers, network names, MAC addresses, and coordinates are removed. Distances are rounded. The method changes these examples led to are summarised in the [Research Log](../blueprint/research-log.md).

!!! note "Expected outputs"
    v0.2 outputs come from replaying the v0.2 code on a country ledger. v0.3 outputs are the outputs the v0.3 design is expected to produce; they become measured outputs once the v0.3 code lands.

## Example A: One Fixed Router, Short Window

**Telemetry:** One device, one associated router, 7 rows over 3 days. Six rows sit within a few metres of each other. The first reading after start-up lands about 400 m away.

**Registry:** The official pin is about 15 km from the cluster.

| | v0.2 | v0.3 (expected) |
| --- | --- | --- |
| Device class | `HIGH_MOBILITY` (6/7 rows inside the geofence, below 90%) | `STATIONARY` (one supported cluster, one noise event) |
| Track 1 | `MINOR_DISCREPANCY`, score 53.7 | `GOVT_PIN_MISMATCH`, `MEDIUM`, `FIELD_VERIFY` |
| Track 2 | no tags | no tags |
| Track 3 | — | `UNRESOLVED` (network name does not reference the facility) |

**Why it is hard:** The device is clearly stationary, but a single device on a residential-style network cannot show whether it sits in the facility or somewhere else. The pin may be wrong, or the device may be installed elsewhere.

## Example B: Mostly Wired, One Off-Site Day

**Telemetry:** One device over seven weeks. About two thirds of rows have no associated Wi-Fi (wired or unassociated). The remainder use a network whose name matches the registered facility name. On one day the device appears about 90 km away on a residential network.

**Registry:** The official pin is about 17 km from the main cluster.

| | v0.2 | v0.3 (expected) |
| --- | --- | --- |
| Facility centroid | Average of all rows, dragged toward the off-site day; about 38 km from the pin | Main cluster only; about 17 km from the pin |
| Device class | `HIGH_MOBILITY` (0% compliance against the dragged centroid) | `STATIONARY` (off-site day is unsupported noise) |
| Track 1 | `MINOR_DISCREPANCY`, score 57.5 | `GOVT_PIN_MISMATCH`, confidence limited by about 110–135 m accuracy, `FIELD_VERIFY` |
| Track 2 | `BSSID_SPATIAL_SPLIT` | no split (only one supported cluster) |
| Track 3 | — | `CONSISTENT` (network name matches the registry name) |

**Why it is hard:** The first reading suggests the device is at a different facility. The network name instead points to a registry pin that is far off. v0.2 hid a 38 km offset under its mildest flag.

## Example C: Commuter Laptop Over a School Holiday

**Telemetry:** One laptop over ten weeks. On school days early in the window it connects to a network named after the facility, about 300 m from the official pin. It also uses two home networks about 3 km away. After the term ends it stays at home. In many rows the coordinates are copied from the previous row even though the associated network changed.

| | v0.2 | v0.3 (expected) |
| --- | --- | --- |
| Hotspot tagging | 100% of rows tagged, because carried coordinates made both fixed routers look as if they moved | Only the few genuine phone-hotspot events tagged |
| Facility centroid | Facility network's rows mixed both locations; centroid about 1.9 km from the pin | Govt proximity picks the facility cluster; telemetry dominance picks the home cluster |
| Device class | `COMMUTER` | `COMMUTER` |
| Track 1 | `GOVT_PIN_MISMATCH`, score 75.8 | Strategies disagree; the registry name match picks the facility cluster: `CAMPUS_DISPERSION` (about 300 m), `anchor_resolved_by = ssid_name_match` |
| Track 2 | `HOTSPOT_TETHERED_FACILITY` | `COMMUTER_DEVICE` |
| Track 3 | — | `CONSISTENT` |

**Why it is hard:** By volume, the home is the dominant location because the window spans a holiday. Without the name match the honest answer is `AMBIGUOUS_MULTI_CLUSTER`. A term calendar is not modelled in v0.3.
