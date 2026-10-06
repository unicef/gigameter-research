"""Tests for SpatialConfig, geo helpers, fix events, and local-time enrichment."""

import pandas as pd
import pytest

from spatial_fixtures import (
    A_SITE,
    C_HOME,
    C_HOME_BSSID,
    C_SCHOOL,
    C_SCHOOL_BSSID,
    example_a,
    example_b,
    example_c,
    offset,
)
from src.spatial_intelligence.config import DEFAULT_CONFIG, SpatialConfig
from src.spatial_intelligence.fix_events import build_fix_event_table, mark_fix_events
from src.spatial_intelligence.geo import (
    NOISE_LABEL,
    dbscan_labels,
    haversine_m,
    max_pairwise_distance_m,
    weighted_centroid,
)
from src.utils.data_loader import TelemetryLoader


# ---------------------------------------------------------------------------
# SpatialConfig
# ---------------------------------------------------------------------------
def test_config_hash_is_stable_and_changes_with_settings() -> None:
    assert SpatialConfig().config_hash == DEFAULT_CONFIG.config_hash
    changed = DEFAULT_CONFIG.with_overrides(anchor_eps_m=175.0)
    assert changed.config_hash != DEFAULT_CONFIG.config_hash
    assert DEFAULT_CONFIG.provenance() == {
        "methodology_version": "0.3",
        "config_hash": DEFAULT_CONFIG.config_hash,
    }


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"verified_max_m": 600.0}, "verified_max_m"),
        ({"coherence_full_m": 2500.0}, "coherence_full_m"),
        ({"device_min_samples": 1}, "device_min_samples"),
        ({"operational_hours": (20, 8)}, "operational_hours"),
        ({"strategies": ("closest_pin",)}, "strategies"),
        ({"confidence_medium_min": 80.0}, "confidence_medium_min"),
    ],
)
def test_config_rejects_contradictory_settings(changes: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        DEFAULT_CONFIG.with_overrides(**changes)


# ---------------------------------------------------------------------------
# geo helpers
# ---------------------------------------------------------------------------
def test_weighted_centroid_favours_precise_points() -> None:
    far = offset(A_SITE, 100, 0)
    lat, lon = weighted_centroid(
        [A_SITE[0], far[0]], [A_SITE[1], far[1]], [10.0, 100.0]
    )
    assert haversine_m(lat, lon, *A_SITE) < 2.0


def test_weighted_centroid_fills_missing_accuracy_with_median() -> None:
    lat, _ = weighted_centroid([0.0, 1.0, 2.0], [0.0, 0.0, 0.0], [10.0, None, 10.0])
    assert lat == pytest.approx(1.0)


def test_dbscan_labels_mark_isolated_point_as_noise() -> None:
    cluster = [offset(A_SITE, n, 0) for n in (0, 5, 10, 15)]
    stray = offset(A_SITE, 400, 0)
    points = cluster + [stray]
    labels = dbscan_labels([p[0] for p in points], [p[1] for p in points], 150.0, 3)
    assert len(set(labels[:4])) == 1 and labels[0] != NOISE_LABEL
    assert labels[4] == NOISE_LABEL


def test_max_pairwise_distance() -> None:
    a, b, c = A_SITE, offset(A_SITE, 1000, 0), offset(A_SITE, 0, 500)
    dist = max_pairwise_distance_m([a[0], b[0], c[0]], [a[1], b[1], c[1]])
    assert dist == pytest.approx(1118.0, rel=0.01)
    assert max_pairwise_distance_m([a[0]], [a[1]]) == 0.0


# ---------------------------------------------------------------------------
# Fix events
# ---------------------------------------------------------------------------
def test_example_a_bursts_collapse_and_fresh_repeats_count() -> None:
    events = build_fix_event_table(example_a())
    # 7 rows: one outlier, one burst pair, one same-fix pair 35 minutes apart
    # (two events), and a final burst pair.
    assert len(events) == 5
    assert events["row_count"].tolist() == [1, 2, 1, 1, 2]
    assert not events["fix_carried"].any()
    assert events["local_date"].nunique() == 3


def test_example_c_marks_coordinates_carried_across_networks() -> None:
    marked = mark_fix_events(example_c())
    carried = marked[marked["fix_carried"]]
    assert not carried.empty

    # Morning rows under the school network that still carry the home fix.
    school_rows_near_home = carried[carried["detected_wifi_bssid"] == C_SCHOOL_BSSID]
    assert not school_rows_near_home.empty
    assert (
        haversine_m(
            school_rows_near_home["detected_latitude"],
            school_rows_near_home["detected_longitude"],
            *C_HOME,
        )
        < 100
    ).all()

    # Afternoon rows under the home network that still carry the school fix.
    home_rows_near_school = carried[carried["detected_wifi_bssid"] == C_HOME_BSSID]
    assert (
        haversine_m(
            home_rows_near_school["detected_latitude"],
            home_rows_near_school["detected_longitude"],
            *C_SCHOOL,
        )
        < 100
    ).all()

    # After removing carried rows, each network only appears near its own place.
    events = build_fix_event_table(marked)
    school_events = events[events["detected_wifi_bssid"] == C_SCHOOL_BSSID]
    assert (
        haversine_m(
            school_events["detected_latitude"], school_events["detected_longitude"], *C_SCHOOL
        )
        < 100
    ).all()


def test_rows_without_a_network_never_carry_or_set_origin() -> None:
    marked = mark_fix_events(example_b())
    no_bssid = marked["detected_wifi_bssid"].isna()
    assert not marked.loc[no_bssid, "fix_carried"].any()
    school_rows = marked[marked["detected_wifi_bssid"].notna() & (marked["detected_wifi_ssid"] == "Shkolla Gamma")]
    assert not school_rows["fix_carried"].any()


def test_fix_events_drop_null_coordinates_and_mark_workdays() -> None:
    frame = example_a()
    frame.loc[0, "detected_latitude"] = None
    marked = mark_fix_events(frame)
    assert len(marked) == len(frame) - 1
    assert marked["is_workday"].all()

    weekend_only = DEFAULT_CONFIG.with_overrides(workdays=(5, 6))
    assert not mark_fix_events(frame, weekend_only)["is_workday"].any()


def test_burst_window_is_configurable() -> None:
    wide = DEFAULT_CONFIG.with_overrides(burst_window_s=3600.0)
    assert len(build_fix_event_table(example_a(), wide)) == 4


def test_empty_frame_returns_empty_event_table() -> None:
    empty = example_a().iloc[0:0]
    assert build_fix_event_table(empty).empty


# ---------------------------------------------------------------------------
# Local-time enrichment
# ---------------------------------------------------------------------------
def test_enrichment_keeps_tz_name_and_converts_each_timezone() -> None:
    raw = pd.DataFrame(
        {
            "school_id_giga": ["TIRANE", "TIRANE", "MANILA"],
            "device_id": ["D1", "D1", "D2"],
            "detected_latitude": [41.33, 41.33, 14.60],
            "detected_longitude": [19.82, 19.82, 120.98],
            "created_timestamp": [
                "2026-07-01T06:30:00Z",
                "2026-07-01T18:30:00Z",
                "2026-07-01T23:30:00Z",
            ],
            "govt_latitude": [41.33, 41.33, 14.60],
            "govt_longitude": [19.82, 19.82, 120.98],
        }
    )

    loaded = TelemetryLoader().load(telemetry_df=raw)

    assert loaded["tz_name"].tolist() == ["Europe/Tirane", "Europe/Tirane", "Asia/Manila"]
    assert loaded["local_hour"].tolist() == [8, 20, 7]
    assert loaded["is_operational_hours"].tolist() == [True, False, False]
    assert str(loaded["local_date"].iloc[2]) == "2026-07-02"
