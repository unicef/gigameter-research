# FacilityValidator

Pillar 3 and the entry point for most analyses: runs the full chain on construction and scores every facility on the three tracks. The rules are in [Blueprint Section 6](../blueprint/technical_blueprint.md#6-facilityvalidator-scoring-tracks), and the output columns in [Section 7](../blueprint/technical_blueprint.md#7-output-schema).

::: src.spatial_intelligence.facility_validator.FacilityValidator
    options:
      filters: ["!^_", "!^plot_"]

## Plots

Each returns a `plotly.graph_objects.Figure`.

::: src.spatial_intelligence.facility_validator.FacilityValidator.plot_stationary_facility_percentage
    options:
      heading_level: 3

::: src.spatial_intelligence.facility_validator.FacilityValidator.plot_facility_map
    options:
      heading_level: 3

::: src.spatial_intelligence.facility_validator.FacilityValidator.plot_facility_evidence_timeline
    options:
      heading_level: 3

::: src.spatial_intelligence.facility_validator.FacilityValidator.plot_score_breakdown
    options:
      heading_level: 3

::: src.spatial_intelligence.facility_validator.FacilityValidator.plot_location_triage
    options:
      heading_level: 3

::: src.spatial_intelligence.facility_validator.FacilityValidator.plot_flag_confidence_breakdown
    options:
      heading_level: 3
