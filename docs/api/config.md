# Configuration

`SpatialConfig` holds every numeric setting of the methodology: distances, day counts, score weights and thresholds. It is frozen, so a run cannot change its settings halfway. `DEFAULT_CONFIG` is the published v0.3 configuration; the value and reason for each setting are on the [Parameters](../blueprint/parameters.md) page.

```python
from src.spatial_intelligence.config import DEFAULT_CONFIG

custom = DEFAULT_CONFIG.with_overrides(device_eps_m=200.0, workdays=(0, 1, 2, 3, 4, 5))
custom.provenance()   # {"methodology_version": "0.3", "config_hash": "..."}
```

`with_overrides` returns a new config and checks it: contradictory settings, such as `verified_max_m` not below `mismatch_min_m`, raise `ValueError`.

Every output row is stamped with `methodology_version` and `config_hash`. Two rows with the same hash were produced with identical settings.

## Strategy Names

Values accepted in `strategies`:

| Constant | Value |
| --- | --- |
| `STRATEGY_GOVT_PROXIMITY` | `govt_proximity_anchor` |
| `STRATEGY_TELEMETRY_DOMINANCE` | `telemetry_dominance` |
| `STRATEGY_STATIONARY_FIRST` | `stationary_first` |

The default runs the first two and reports whether they agree ([Blueprint Section 5.4](../blueprint/technical_blueprint.md#54-strategy-candidates-agreement)). Strategies are passed as these strings, for example `FacilityValidator(..., strategies=["govt_proximity_anchor", "stationary_first"])`. The same names are available as an enum; pass a member's `.value`, not the member itself:

::: src.spatial_intelligence.spatial_profiler.ClusterResolutionStrategy
    options:
      heading_level: 3
      show_if_no_docstring: true

## SpatialConfig

Fields are listed in the same groups as on the [Parameters](../blueprint/parameters.md) page: evidence and time window, hotspot and BSSID mobility, device mobility, facility anchor, raw score, and Tracks 1 to 3.

::: src.spatial_intelligence.config.SpatialConfig
    options:
      show_if_no_docstring: true
