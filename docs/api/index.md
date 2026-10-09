# Python API Overview

The spatial methodology is implemented in the `src.spatial_intelligence` package, with data loading in `src.utils`. This page shows how the pieces fit together. The pages that follow document every public class and function, generated from the code.

Code is imported from the repository root, for example `from src.spatial_intelligence.facility_validator import FacilityValidator`. Run notebooks and scripts with the repository root as the working directory.

## Quick Start

`FacilityValidator` runs the whole chain, so most analyses start and end with it:

```python
from src.spatial_intelligence.facility_validator import FacilityValidator

validator = FacilityValidator(
    file_path="data/spatial_confidence_ledger/ALB/ALB_spatial_confidence_ledger_05-08-2026.csv",
)

audit = validator.run_national_facility_audit()   # one row per facility
audit["location_verification_flag"].value_counts()

one = validator.evaluate_facility_location_confidence(audit["school_id_giga"].iloc[0])
one["recommended_action"], one["score_breakdown"]
```

The audit columns are described in [Blueprint Section 7](../blueprint/technical_blueprint.md#7-output-schema). Every row carries `methodology_version` and `config_hash`, so results from different settings can be told apart.

Telemetry can come from three sources; give exactly one:

| Argument | Source |
| --- | --- |
| `telemetry_df` | A pandas DataFrame already in memory |
| `file_path` | A `.csv` or `.parquet` ledger |
| `query_name` and `query_params` | A SQL template under `sql/`, run against the database configured in `.env` |

Official pins come from the ledger when it has `govt_latitude` and `govt_longitude`, otherwise from Delta Sharing with `country_iso3`. Track 3 needs the pins of every facility in the country, not only those in the telemetry; pass `country_iso3="ALB", load_entity_pins=True` to load them, or pass a table as `entity_pins`. `validator.entity_pins_source` records which was used.

## Processing Order

Constructing a `FacilityValidator` runs these steps once. Results are cached, so later calls are cheap.

| Step | Component | What it produces |
| --- | --- | --- |
| 1 | [`TelemetryLoader`](loading.md) | Canonical columns, official pins, local time |
| 2 | [`SpatialProfiler`](profiler.md) (on construction) | Hotspot and BSSID mobility tags, fix events |
| 3 | [`MobilityAnalyzer`](mobility.md) | One mobility class per device |
| 4 | [`SpatialProfiler.build_facility_spatial_summary`](profiler.md) | Observation clusters and one anchor per facility |
| 5 | [`FacilityValidator`](validator.md) | S\_raw and the three tracks per facility |

The intermediate objects stay available on the validator:

| Attribute | Contents |
| --- | --- |
| `validator.df` | The canonical telemetry frame |
| `validator.valid_geo_df` | Rows with Wi-Fi coordinates (the no-IP rule applied) |
| `validator.spatial_profiler` | The `SpatialProfiler`, with `fix_events` and `build_bssid_profiles()` |
| `validator.mobility_analyzer` | The `MobilityAnalyzer`, with `generate_facility_mobility_report()` for device classes |
| `validator.facility_summary` | One row per facility from anchor selection |
| `validator.config` | The `SpatialConfig` used |

## Changing Settings

All numeric settings live in one [`SpatialConfig`](config.md). To try a different value, derive a copy and pass it in:

```python
from src.spatial_intelligence.config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.with_overrides(anchor_eps_m=200.0)
validator = FacilityValidator(file_path=..., config=config)
```

The copy is validated when it is created, and its `config_hash` differs from the default, so its outputs are stamped accordingly. The defaults and their reasons are on the [Parameters](../blueprint/parameters.md) page.

## Using the Components Separately

`MobilityAnalyzer` and `SpatialProfiler` accept the same data arguments as `FacilityValidator` and can be used on their own, for example to study devices without scoring facilities:

```python
from src.spatial_intelligence.mobility_analyzer import MobilityAnalyzer

mobility = MobilityAnalyzer(file_path=...)
devices = mobility.generate_facility_mobility_report()   # one row per device
```

Run alone, `MobilityAnalyzer` measures the geofence audit against each device's dominant cluster, because no facility anchors are known yet.

## Plots

Classes also provide Plotly figures used by the research dashboard. They are listed under **Plots** on each class page and return a `plotly.graph_objects.Figure`.
