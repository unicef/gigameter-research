## Pillar 3: Government Data Validation & Administrative Map Auditing

!!! note "v0.3 draft"
    This page describes the v0.3 design. Code still implements v0.2. Settings are on the [Parameters](../blueprint/parameters.md) page.

### 1\. Why This Pillar Exists

National Ministries of Education and telecommunications authorities maintain registries with official coordinates for public schools and health centers. These registries often contain legacy mapping errors:

*   School pins are placed at the center of a village, district office, or capital city rather than on the building.
*   New or relocated facilities are registered with estimated coordinates.

Telemetry can also be misleading: a device may be installed at a home or at another facility. Pillar 3 therefore asks two questions separately: does the government pin match where the telemetry is (Track 1), and is that telemetry attributable to this entity (Track 3)? Hardware reliability (Track 2) never hides either answer.

### 2\. Core Research Objectives

*   **Empirical Displacement:** Haversine distance (D\_govt) between the anchor centroid and the official pin, always reported when both exist.
*   **Multi-Track Decoupling:**
    *   **Track 1 (Location Truth):** Distance-band flag plus a separate confidence tier and recommended action.
    *   **Track 2 (Hardware Integrity):** S\_raw x P\_coherence and hardware anomaly tags.
    *   **Track 3 (Entity Attribution):** Registry name match and nearest other registered entity.
*   **Track 1 Flags:**
    *   `VERIFIED_ACCURATE`: Anchor within `verified_max_m` of the pin.
    *   `CAMPUS_DISPERSION`: Between `verified_max_m` and `mismatch_min_m`.
    *   `GOVT_PIN_MISMATCH`: Beyond `mismatch_min_m`.
    *   `AMBIGUOUS_MULTI_CLUSTER`: Strategies chose different clusters and no name match resolves them.
    *   `UNSTABLE_MOBILE_ONLY`: No supported anchor cluster.
    *   `NO_GOVT_PIN_AVAILABLE`, `INSUFFICIENT_DATA`.
*   **Recommended Actions:** `SUBMIT_CORRECTION` only for high-confidence, multi-device mismatches; `FIELD_VERIFY` for single-device or medium-confidence results; `AWAIT_DATA` for low confidence.

### 3\. Output Schema

```json title="Facility Evaluation Payload (v0.3 draft)"
{
  "school_id_giga": "SCH_12345",
  "methodology_version": "0.3",
  "location_verification_flag": "VERIFIED_ACCURATE",
  "location_confidence_score": 82.5,
  "location_confidence_level": "HIGH",
  "recommended_action": "NONE",
  "govt_displacement_m": 34.2,
  "strategy_agreement": true,
  "anchor_resolved_by": "strategy_agreement",
  "hardware_health_score": 8.25,
  "hardware_anomaly_tags": ["BSSID_SPATIAL_SPLIT", "COMMUTER_DEVICE"],
  "entity_attribution_flag": "CONSISTENT",
  "ssid_name_match": true
}
```

The full schema is in [Blueprint Section 7](../blueprint/technical_blueprint.md#7-output-schema).
