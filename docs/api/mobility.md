# MobilityAnalyzer

Pillar 1: classifies each device from its own fix events, without using any facility location. The rules are in [Blueprint Section 4](../blueprint/technical_blueprint.md#4-pillar-1-mobilityanalyzer-logic).

::: src.spatial_intelligence.mobility_analyzer.MobilityAnalyzer
    options:
      filters: ["!^_", "!^plot_"]

## Plots

Each returns a `plotly.graph_objects.Figure`.

::: src.spatial_intelligence.mobility_analyzer.MobilityAnalyzer.plot_device_mobility_map
    options:
      heading_level: 3

::: src.spatial_intelligence.mobility_analyzer.MobilityAnalyzer.plot_cluster_calendar
    options:
      heading_level: 3

::: src.spatial_intelligence.mobility_analyzer.MobilityAnalyzer.plot_displacement_timeline
    options:
      heading_level: 3

::: src.spatial_intelligence.mobility_analyzer.MobilityAnalyzer.plot_commuter_time_of_day_scatter
    options:
      heading_level: 3

::: src.spatial_intelligence.mobility_analyzer.MobilityAnalyzer.plot_national_mobility_distribution
    options:
      heading_level: 3
