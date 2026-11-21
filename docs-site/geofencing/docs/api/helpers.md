# Helpers & Constants

Lower-level functions used by the analysis classes. They are useful on their own for custom analyses, for example to compute fix events for a subset of rows.

## Output Values

The string values that appear in outputs. Each is also a constant in the module named, so code can compare against the constant instead of a literal.

**Track 1 flags** (`facility_validator`, `FLAG_*`): `VERIFIED_ACCURATE`, `CAMPUS_DISPERSION`, `GOVT_PIN_MISMATCH`, `AMBIGUOUS_MULTI_CLUSTER`, `UNSTABLE_MOBILE_ONLY`, `NO_GOVT_PIN_AVAILABLE`, `INSUFFICIENT_DATA`.

**Recommended actions** (`facility_validator`, `ACTION_*`): `SUBMIT_CORRECTION`, `FIELD_VERIFY`, `AWAIT_DATA`, `NONE`.

**Track 3 attribution** (`facility_validator`, `ATTRIBUTION_*`): `CONSISTENT`, `OTHER_ENTITY_NEARBY`, `UNRESOLVED`.

**Track 3 pin source** (`facility_validator`, `PINS_FROM_*`): `entity_pins` (passed in), `delta_sharing` (loaded), `telemetry_pins` (only facilities in the telemetry).

**Mobility classes** (`mobility_analyzer.MOBILITY_CLASSES`): `STATIONARY`, `COMMUTER`, `RELOCATED`, `HIGH_MOBILITY`, `INSUFFICIENT_EVIDENCE`.

**Geofence reference** (`mobility_analyzer`, `REFERENCE_*`): `facility_anchor`, `device_dominant_cluster`.

**Anchor resolution** (`spatial_profiler`, `RESOLVED_BY_*`): `strategy_agreement`, `single_strategy`, `ssid_name_match`, `unresolved`, `no_cluster`.

**Strategy fallback reasons** (`spatial_profiler`, `FALLBACK_*`): `no_govt_pin`, `no_cluster_within_govt_anchor_radius`, `no_device_classes`, `no_stationary_evidence`.

Their meaning is defined in the [Blueprint](../blueprint/technical_blueprint.md). Colours used for these values in plots are in `src.spatial_intelligence.palette`.

## Fix Events

::: src.spatial_intelligence.fix_events.mark_fix_events

::: src.spatial_intelligence.fix_events.build_fix_event_table

## Geometry

::: src.spatial_intelligence.geo.haversine_m

::: src.spatial_intelligence.geo.weighted_centroid

::: src.spatial_intelligence.geo.dbscan_labels

::: src.spatial_intelligence.geo.max_pairwise_distance_m

## Registry Name Matching

::: src.spatial_intelligence.name_match.distinctive_tokens

::: src.spatial_intelligence.name_match.ssid_matches_name

## BSSID Helpers

::: src.spatial_intelligence.spatial_profiler.is_locally_administered
