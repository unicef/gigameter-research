# SpatialProfiler

Pillar 2: tags hotspots and mobile BSSIDs, builds fix events, and selects one anchor cluster per facility. The rules are in [Blueprint Section 5](../blueprint/technical_blueprint.md#5-pillar-2-spatialprofiler-logic).

::: src.spatial_intelligence.spatial_profiler.SpatialProfiler
    options:
      filters: ["!^_", "!^plot_"]

## Plots

Each returns a `plotly.graph_objects.Figure`.

::: src.spatial_intelligence.spatial_profiler.SpatialProfiler.plot_signal_vs_accuracy_density
    options:
      heading_level: 3

::: src.spatial_intelligence.spatial_profiler.SpatialProfiler.plot_accuracy_ecdf
    options:
      heading_level: 3

::: src.spatial_intelligence.spatial_profiler.SpatialProfiler.plot_daily_coverage
    options:
      heading_level: 3

::: src.spatial_intelligence.spatial_profiler.SpatialProfiler.plot_bssid_temporal_profile
    options:
      heading_level: 3
