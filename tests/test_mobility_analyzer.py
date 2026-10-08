from datetime import datetime, timedelta

import pandas as pd
import pytest

from src.spatial_intelligence.config import DEFAULT_CONFIG
from src.spatial_intelligence.mobility_analyzer import (
    REFERENCE_DEVICE_DOMINANT,
    REFERENCE_FACILITY_ANCHOR,
    MobilityAnalyzer,
)
from spatial_fixtures import (
    A_SITE,
    C_HOME,
    C_SCHOOL,
    ORIGIN,
    example_a,
    example_b,
    example_c,
    frame,
    offset,
    row,
)


def _analyze(df, device_id, **kwargs):
    analyzer = MobilityAnalyzer(telemetry_df=df, **kwargs)
    return analyzer, analyzer.analyze_device_mobility(device_id)


def _daily_rows(device, site, days, start, bssid):
    rows = []
    for day in range(days):
        when = start + timedelta(days=day)
        for hour in (9, 13, 17):
            rows.append(
                row(school="SCH_X", device=device, when=when.replace(hour=hour),
                    point=offset(site, hour % 3, 0), accuracy=20.0, bssid=bssid,
                    ssid="Net", govt=ORIGIN, school_name="School X")
            )
    return rows


def test_example_a_is_stationary_with_one_outlier():
    _, result = _analyze(example_a(), "DEV_A")

    assert result["mobility_class"] == "STATIONARY"
    assert result["total_scans"] == 7
    assert result["total_fix_events"] == 5
    assert result["evidence_device_days"] == 3
    assert result["supported_cluster_count"] == 1
    assert result["noise_share"] == pytest.approx(0.2)
    assert result["dominant_cluster_device_days"] == 3
    assert result["reference_source"] == REFERENCE_DEVICE_DOMINANT
    assert result["dominant_centroid_lat"] == pytest.approx(A_SITE[0], abs=5e-4)
    assert result["methodology_version"] == DEFAULT_CONFIG.methodology_version
    assert result["config_hash"] == DEFAULT_CONFIG.config_hash


def test_example_b_offsite_day_is_noise_not_a_second_place():
    _, result = _analyze(example_b(), "DEV_B")

    assert result["mobility_class"] == "STATIONARY"
    assert result["supported_cluster_count"] == 1
    events = result["processed_df"]
    apartment = events[events["detected_wifi_ssid"] == "APT_X"]
    assert not apartment["is_supported_cluster"].any()


def test_example_c_is_commuter_and_home_dominates():
    _, result = _analyze(example_c(), "DEV_C")

    assert result["mobility_class"] == "COMMUTER"
    assert result["supported_cluster_count"] == 2
    assert result["cluster_transitions"] >= DEFAULT_CONFIG.commuter_min_alternations
    assert result["carried_scans"] > 0
    assert result["total_fix_events"] < result["total_scans"]
    assert result["dominant_centroid_lat"] == pytest.approx(C_HOME[0], abs=1e-3)
    assert result["dominant_centroid_lon"] == pytest.approx(C_HOME[1], abs=1e-3)


def test_sequential_sites_are_relocated():
    first = ORIGIN
    second = offset(ORIGIN, 5_000, 0)
    start = datetime(2026, 3, 2)
    rows = _daily_rows("DEV_R", first, 10, start, "aa:00:00:00:00:01")
    rows += _daily_rows("DEV_R", second, 10, start + timedelta(days=10), "aa:00:00:00:00:02")
    _, result = _analyze(frame(rows), "DEV_R")

    assert result["supported_cluster_count"] == 2
    assert result["cluster_transitions"] == 1
    assert result["mobility_class"] == "RELOCATED"


def test_scattered_device_is_high_mobility():
    start = datetime(2026, 3, 2)
    rows = [
        row(school="SCH_X", device="DEV_H", when=(start + timedelta(days=i)).replace(hour=10),
            point=offset(ORIGIN, i * 1_000, 0), accuracy=20.0, bssid=f"aa:00:00:00:01:{i:02x}",
            ssid="Net", govt=ORIGIN, school_name="School X")
        for i in range(8)
    ]
    _, result = _analyze(frame(rows), "DEV_H")

    assert result["supported_cluster_count"] == 0
    assert result["dominant_cluster_id"] is None
    assert result["reference_source"] is None
    assert result["mobility_class"] == "HIGH_MOBILITY"


@pytest.mark.parametrize(
    "days, hours",
    [
        (1, (9, 11, 13, 15, 17)),  # many events on a single day
        (2, (10,)),  # two days, fewer events than device_min_samples
    ],
)
def test_thin_evidence_is_not_called_mobile(days, hours):
    start = datetime(2026, 3, 2)
    rows = [
        row(school="SCH_X", device="DEV_T", when=(start + timedelta(days=d)).replace(hour=h),
            point=offset(ORIGIN, d * 1.0, 0), accuracy=20.0, bssid=f"aa:00:00:00:02:{h:02x}",
            ssid="Net", govt=ORIGIN, school_name="School X")
        for d in range(days)
        for h in hours
    ]
    _, result = _analyze(frame(rows), "DEV_T")

    assert result["mobility_class"] == "INSUFFICIENT_EVIDENCE"
    assert result["evidence_device_days"] == days


def test_facility_anchor_is_the_audit_reference_when_given():
    df = example_c()
    summary = pd.DataFrame(
        {
            "school_id_giga": ["SCH_C"],
            "empirical_centroid_lat": [C_SCHOOL[0]],
            "empirical_centroid_lon": [C_SCHOOL[1]],
        }
    )
    _, anchored = _analyze(df, "DEV_C", facility_summary=summary)
    _, unanchored = _analyze(df, "DEV_C")

    assert anchored["reference_source"] == REFERENCE_FACILITY_ANCHOR
    assert anchored["mobility_class"] == unanchored["mobility_class"]
    assert anchored["dominant_cluster_id"] == unanchored["dominant_cluster_id"]
    assert anchored["compliance_rate_pct"] < unanchored["compliance_rate_pct"]


def test_geofence_override_and_cache():
    analyzer = MobilityAnalyzer(telemetry_df=example_a(), geofence_radius_m=500)

    assert analyzer.config.geofence_radius_m == 500
    first = analyzer.analyze_device_mobility("DEV_A")
    assert analyzer.analyze_device_mobility("DEV_A") is first
    assert first["compliance_rate_pct"] == 100.0

    analyzer.set_geofence_radius(1.0)
    narrowed = analyzer.analyze_device_mobility("DEV_A")
    assert analyzer.config.geofence_radius_m == 1.0
    assert narrowed["config_hash"] != first["config_hash"]
    assert narrowed["compliance_rate_pct"] < first["compliance_rate_pct"]
    assert narrowed["mobility_class"] == first["mobility_class"]


def test_report_and_event_table_cover_all_devices():
    df = pd.concat([example_a(), example_c()], ignore_index=True)
    analyzer = MobilityAnalyzer(telemetry_df=df)

    report = analyzer.generate_facility_mobility_report()
    assert set(report["device_id"]) == {"DEV_A", "DEV_C"}
    assert "processed_df" not in report.columns
    assert {"evidence_device_days", "dominant_cluster_id", "config_hash"} <= set(report.columns)

    events = analyzer.build_device_event_table()
    assert set(events["mobility_class"]) == {"STATIONARY", "COMMUTER"}
    assert not events["fix_carried"].any()


def test_plots_render_for_each_example():
    analyzer = MobilityAnalyzer(telemetry_df=example_c())
    for plot in (
        analyzer.plot_device_mobility_map,
        analyzer.plot_displacement_timeline,
        analyzer.plot_commuter_time_of_day_scatter,
        analyzer.plot_cluster_calendar,
    ):
        assert plot("DEV_C").data
    assert analyzer.plot_national_mobility_distribution().data
