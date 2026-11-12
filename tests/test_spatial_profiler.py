from datetime import datetime, timedelta

import pandas as pd
import pytest

from src.spatial_intelligence.config import (
    DEFAULT_CONFIG,
    STRATEGY_GOVT_PROXIMITY,
    STRATEGY_STATIONARY_FIRST,
    STRATEGY_TELEMETRY_DOMINANCE,
)
from src.spatial_intelligence.mobility_analyzer import MobilityAnalyzer
from src.spatial_intelligence.name_match import distinctive_tokens, ssid_matches_name
from src.spatial_intelligence.spatial_profiler import (
    FALLBACK_NO_CLUSTER_IN_RADIUS,
    RESOLVED_BY_AGREEMENT,
    RESOLVED_BY_NAME_MATCH,
    RESOLVED_BY_UNRESOLVED,
    SpatialProfiler,
    is_locally_administered,
)
from spatial_fixtures import (
    A_SITE,
    B_SCHOOL_BSSID,
    B_SITE,
    C_HOME,
    C_PHONE_BSSID,
    C_SCHOOL,
    C_SCHOOL_BSSID,
    ORIGIN,
    example_a,
    example_b,
    example_c,
    frame,
    offset,
    row,
)


def _summary(df, **kwargs):
    profiler = SpatialProfiler(df)
    summary = profiler.build_facility_spatial_summary(**kwargs)
    return profiler, summary.iloc[0]


def test_example_a_anchor_is_the_router_cluster_far_from_the_pin():
    profiler, s = _summary(example_a())

    assert s["anchor_resolved_by"] == RESOLVED_BY_AGREEMENT
    assert s["strategy_agreement"]
    assert s["anchor_supported"]
    assert s["anchor_support_device_days"] == 3
    assert s["cluster_count"] == 2
    assert s["supported_cluster_count"] == 1
    assert s["empirical_centroid_lat"] == pytest.approx(A_SITE[0], abs=5e-4)
    assert s["govt_displacement_m"] == pytest.approx(15_000, rel=0.02)
    assert FALLBACK_NO_CLUSTER_IN_RADIUS in s["strategy_fallback_reason"]
    assert not s["ssid_name_match"]
    assert s["methodology_version"] == DEFAULT_CONFIG.methodology_version
    assert len(profiler.facility_clusters) == 2


def test_example_b_no_bssid_and_school_ssid_events_form_one_anchor():
    _, s = _summary(example_b())

    assert s["anchor_supported"]
    assert s["supported_cluster_count"] == 1
    assert s["empirical_centroid_lat"] == pytest.approx(B_SITE[0], abs=5e-4)
    assert B_SCHOOL_BSSID in s["anchor_bssids"]
    assert s["ssid_name_match"]
    assert s["split_distance_m"] == 0.0


def test_example_c_strategies_disagree_and_name_match_picks_the_school():
    _, s = _summary(example_c())

    assert s["strategy_candidates"][STRATEGY_GOVT_PROXIMITY] != s["strategy_candidates"][
        STRATEGY_TELEMETRY_DOMINANCE
    ]
    assert not s["strategy_agreement"]
    assert s["anchor_resolved_by"] == RESOLVED_BY_NAME_MATCH
    assert s["empirical_centroid_lat"] == pytest.approx(C_SCHOOL[0], abs=5e-4)
    assert s["empirical_centroid_lon"] == pytest.approx(C_SCHOOL[1], abs=5e-4)
    assert s["govt_displacement_m"] == pytest.approx(307, abs=15)
    assert C_SCHOOL_BSSID in s["anchor_bssids"]
    assert s["split_distance_m"] == pytest.approx(3_200, rel=0.05)
    distances = s["candidate_govt_displacement_m"]
    assert distances[STRATEGY_TELEMETRY_DOMINANCE] > DEFAULT_CONFIG.govt_anchor_radius_m


def test_one_stray_school_ssid_reading_at_home_does_not_count_as_a_name_match():
    df = example_c()
    stray = row(school="SCH_C", device="DEV_C", when=datetime(2026, 6, 3, 12, 0),
                point=offset(C_HOME, 2, 2), accuracy=18.0, bssid=C_SCHOOL_BSSID,
                ssid="Shkolla Delta Epsilon 2.4G", govt=tuple(df[["govt_latitude", "govt_longitude"]].iloc[0]),
                school_name=df["school_name"].iloc[0])
    _, s = _summary(pd.concat([df, frame([stray])], ignore_index=True))

    assert s["anchor_resolved_by"] == RESOLVED_BY_NAME_MATCH
    assert s["empirical_centroid_lat"] == pytest.approx(C_SCHOOL[0], abs=5e-4)


def test_disagreement_without_name_match_leaves_anchor_unresolved():
    df = example_c()
    df["detected_wifi_ssid"] = df["detected_wifi_ssid"].replace(
        "Shkolla Delta Epsilon 2.4G", "Office-Net"
    )
    _, s = _summary(df)

    assert s["anchor_resolved_by"] == RESOLVED_BY_UNRESOLVED
    assert s["anchor_cluster_id"] is None
    assert pd.isna(s["empirical_centroid_lat"])
    assert set(s["candidate_govt_displacement_m"]) == {
        STRATEGY_GOVT_PROXIMITY,
        STRATEGY_TELEMETRY_DOMINANCE,
    }


def test_stationary_first_follows_the_commuters_dominant_cluster():
    df = example_c()
    cfg = DEFAULT_CONFIG.with_overrides(strategies=(STRATEGY_STATIONARY_FIRST,))
    profiler = SpatialProfiler(df, config=cfg)
    device_events = MobilityAnalyzer(
        telemetry_df=df, fix_event_rows=profiler.fix_event_rows
    ).build_device_event_table()
    s = profiler.build_facility_spatial_summary(device_events=device_events).iloc[0]

    assert s["empirical_centroid_lat"] == pytest.approx(C_HOME[0], abs=1e-3)

    no_classes = profiler.build_facility_spatial_summary().iloc[0]
    assert "no_device_classes" in no_classes["strategy_fallback_reason"]


def test_carried_fixes_do_not_make_the_school_router_mobile():
    profiler = SpatialProfiler(example_c())

    assert C_SCHOOL_BSSID not in profiler.mobile_bssids
    rows = profiler.df
    assert rows.loc[rows["detected_wifi_bssid"] == C_PHONE_BSSID, "is_laa_bssid"].all()
    assert not rows.loc[rows["detected_wifi_bssid"] == C_SCHOOL_BSSID, "is_laa_bssid"].any()
    assert rows.loc[rows["detected_wifi_ssid"] == "iPhone", "is_mobile_hotspot"].all()


def test_router_seen_at_two_places_on_several_days_is_mobile():
    start = datetime(2026, 3, 2)
    rows = []
    for day in range(6):
        place = ORIGIN if day < 3 else offset(ORIGIN, 3_000, 0)
        when = start + timedelta(days=day)
        for hour in (9, 14):
            rows.append(
                row(school="SCH_M", device="DEV_M", when=when.replace(hour=hour),
                    point=offset(place, hour, day), accuracy=30.0, bssid="aa:00:00:00:00:99",
                    ssid="Router", govt=ORIGIN, school_name="School M")
            )
    profiler = SpatialProfiler(frame(rows))

    assert "aa:00:00:00:00:99" in profiler.mobile_bssids
    assert profiler.df["is_mobile_hotspot"].all()


def test_bssid_profiles_report_fix_events_and_carried_rows():
    profiles = SpatialProfiler(example_c()).build_bssid_profiles()
    school = profiles[profiles["detected_wifi_bssid"] == C_SCHOOL_BSSID].iloc[0]

    assert school["carried_observations"] > 0
    assert school["fix_events"] < school["total_observations"]
    assert not school["is_mobile_bssid"]


def test_locally_administered_bit():
    assert is_locally_administered("02:00:00:00:00:06")
    assert not is_locally_administered("00:00:5e:00:53:04")
    assert not is_locally_administered(None)
    assert not is_locally_administered("zz")


@pytest.mark.parametrize(
    ("ssid", "name", "expected"),
    [
        ("Shkolla Gamma", "Shkolla 9-vjeçare Gamma", True),
        ("Shkolla Delta Epsilon 2.4G", "Shkolla 9-vjeçare Delta Epsilon", True),
        ("Delta-5G", "Shkolla 9-vjeçare Delta Epsilon", False),
        ("Home-XXXX-5G", "Shkolla e Bashkuar Alfa Beta", False),
        ("Shkolla", "Shkolla 9-vjeçare", False),
        ("School 12 Main", "School 12 Main", True),
        (None, "Shkolla Gamma", False),
    ],
)
def test_ssid_name_match(ssid, name, expected):
    assert ssid_matches_name([ssid], name) is expected


def test_distinctive_tokens_strip_diacritics_and_grade_labels():
    assert distinctive_tokens("Shkolla 9-vjeçare Example School A") == {"example", "a"}
