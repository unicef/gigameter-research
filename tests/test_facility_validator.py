from datetime import datetime, timedelta

import pandas as pd
import pytest

from src.spatial_intelligence.config import DEFAULT_CONFIG
from src.spatial_intelligence.facility_validator import (
    ACTION_AWAIT,
    ACTION_FIELD_VERIFY,
    ACTION_NONE,
    ACTION_SUBMIT,
    ATTRIBUTION_CONSISTENT,
    ATTRIBUTION_OTHER_NEARBY,
    ATTRIBUTION_UNRESOLVED,
    FLAG_AMBIGUOUS,
    FLAG_DISPERSION,
    FLAG_INSUFFICIENT,
    FLAG_MISMATCH,
    FLAG_VERIFIED,
    PINS_FROM_DELTA,
    PINS_FROM_TELEMETRY,
    FacilityValidator,
)
from spatial_fixtures import (
    A_SITE,
    ORIGIN,
    example_a,
    example_b,
    example_c,
    frame,
    offset,
    row,
)


class FakeDelta:
    def __init__(self, table: pd.DataFrame) -> None:
        self.table = table
        self.calls = []

    def load_table(self, name: str) -> pd.DataFrame:
        self.calls.append(name)
        return self.table.copy()


def _evaluate(df, school_id, **kwargs):
    validator = FacilityValidator(telemetry_df=df, **kwargs)
    return validator, validator.evaluate_facility_location_confidence(school_id)


def _two_stationary_devices(govt):
    rows = []
    start = datetime(2026, 3, 2)
    for device, bssid in (("DEV_1", "aa:00:00:00:00:01"), ("DEV_2", "aa:00:00:00:00:02")):
        for day in range(14):
            when = start + timedelta(days=day)
            if when.weekday() >= 5:
                continue
            for hour in (9, 13):
                rows.append(
                    row(school="SCH_S", device=device, when=when.replace(hour=hour),
                        point=offset(ORIGIN, hour % 3, 1), accuracy=12.0, bssid=bssid,
                        ssid="Net", govt=govt, school_name="School S")
                )
    return frame(rows)


def test_example_a_single_device_mismatch_goes_to_field_verification():
    _, res = _evaluate(example_a(), "SCH_A")

    assert res["location_verification_flag"] == FLAG_MISMATCH
    assert res["govt_displacement_m"] == pytest.approx(15_000, rel=0.02)
    assert res["recommended_action"] == ACTION_FIELD_VERIFY
    assert res["stationary_devices_count"] == 1
    assert res["score_breakdown"]["stability"] == 30.0
    assert res["score_breakdown"]["consensus"] == DEFAULT_CONFIG.consensus_single_device
    assert res["hardware_anomaly_tags"] == []
    assert res["entity_attribution_flag"] == ATTRIBUTION_UNRESOLVED
    assert res["config_hash"] == DEFAULT_CONFIG.config_hash


def test_example_b_main_cluster_only_and_name_match_attribution():
    _, res = _evaluate(example_b(), "SCH_B")

    assert res["location_verification_flag"] == FLAG_MISMATCH
    assert res["govt_displacement_m"] == pytest.approx(16_700, rel=0.03)
    assert res["score_breakdown"]["precision"] == 0.0
    assert "BSSID_SPATIAL_SPLIT" not in res["hardware_anomaly_tags"]
    assert res["recommended_action"] == ACTION_FIELD_VERIFY
    assert res["entity_attribution_flag"] == ATTRIBUTION_CONSISTENT


def test_example_c_name_match_anchor_is_campus_dispersion():
    _, res = _evaluate(example_c(), "SCH_C")

    assert res["anchor_resolved_by"] == "ssid_name_match"
    assert res["location_verification_flag"] == FLAG_DISPERSION
    assert res["govt_displacement_m"] == pytest.approx(307, abs=15)
    assert res["score_breakdown"]["stability"] == DEFAULT_CONFIG.stability_points[1]
    assert set(res["hardware_anomaly_tags"]) == {"BSSID_SPATIAL_SPLIT", "COMMUTER_DEVICE"}
    assert res["p_coherence"] == DEFAULT_CONFIG.coherence_floor
    assert res["hardware_health_score"] == pytest.approx(
        res["location_confidence_score"] * DEFAULT_CONFIG.coherence_floor, abs=0.1
    )
    assert res["entity_attribution_flag"] == ATTRIBUTION_CONSISTENT
    assert res["commuter_devices_count"] == 1


def test_unresolved_disagreement_is_ambiguous():
    df = example_c()
    df["detected_wifi_ssid"] = df["detected_wifi_ssid"].replace("Shkolla Delta Epsilon 2.4G", "Office-Net")
    _, res = _evaluate(df, "SCH_C")

    assert res["location_verification_flag"] == FLAG_AMBIGUOUS
    assert res["recommended_action"] == ACTION_FIELD_VERIFY
    assert pd.isna(res["govt_displacement_m"])
    assert len(res["candidate_govt_displacement_m"]) == 2
    assert res["score_cluster_id"] == res["strategy_candidates"]["telemetry_dominance"]


def test_two_stationary_devices_far_from_pin_submit_a_correction():
    _, res = _evaluate(_two_stationary_devices(offset(ORIGIN, 0, 5_000)), "SCH_S")

    assert res["location_verification_flag"] == FLAG_MISMATCH
    assert res["location_confidence_level"] == "HIGH"
    assert res["anchor_support_devices"] == 2
    assert res["recommended_action"] == ACTION_SUBMIT


def test_pin_at_the_anchor_is_verified():
    _, res = _evaluate(_two_stationary_devices(offset(ORIGIN, 20, 0)), "SCH_S")

    assert res["location_verification_flag"] == FLAG_VERIFIED
    assert res["recommended_action"] == ACTION_NONE
    assert res["entity_attribution_flag"] == ATTRIBUTION_CONSISTENT


def test_single_reading_is_insufficient():
    df = example_a().iloc[:1]
    _, res = _evaluate(df, "SCH_A")

    assert res["location_verification_flag"] == FLAG_INSUFFICIENT
    assert res["recommended_action"] == ACTION_AWAIT


def test_other_entity_pin_next_to_the_anchor():
    neighbour = offset(A_SITE, 40, 0)
    own = example_a()[["govt_latitude", "govt_longitude"]].iloc[0]
    pins = pd.DataFrame(
        {
            "school_id_giga": ["SCH_A", "SCH_OTHER"],
            "latitude": [own["govt_latitude"], neighbour[0]],
            "longitude": [own["govt_longitude"], neighbour[1]],
        }
    )
    _, res = _evaluate(example_a(), "SCH_A", entity_pins=pins)

    assert res["entity_attribution_flag"] == ATTRIBUTION_OTHER_NEARBY
    assert res["nearest_other_entity_id"] == "SCH_OTHER"
    assert res["nearest_other_entity_distance_m"] < DEFAULT_CONFIG.other_entity_radius_m
    assert res["location_verification_flag"] == FLAG_MISMATCH


def test_entity_pins_load_from_delta_only_when_asked():
    table = pd.DataFrame({"giga_id_school": ["SCH_X"], "latitude": [1.0], "longitude": [2.0]})
    store = FakeDelta(table)
    validator = FacilityValidator(
        telemetry_df=example_a(), country_iso3="XXX", delta_store=store, load_entity_pins=True
    )
    assert store.calls == ["XXX"]
    assert validator.entity_pins_source == PINS_FROM_DELTA

    default = FacilityValidator(telemetry_df=example_a(), country_iso3="XXX", delta_store=store)
    assert store.calls == ["XXX"]
    assert default.entity_pins_source == PINS_FROM_TELEMETRY

    with pytest.raises(ValueError, match="country_iso3"):
        FacilityValidator(telemetry_df=example_a(), load_entity_pins=True)


def test_national_audit_and_summary():
    df = pd.concat([example_a(), example_b(), example_c()], ignore_index=True)
    validator = FacilityValidator(telemetry_df=df)

    audit = validator.run_national_facility_audit()
    assert set(audit["school_id_giga"]) == {"SCH_A", "SCH_B", "SCH_C"}
    assert validator.run_national_facility_audit() is audit
    assert {"score_stability", "recommended_action", "entity_attribution_flag", "config_hash"} <= set(audit.columns)

    summary = validator.summarize_national_audit()
    assert summary["total_facilities"] == 3
    assert summary["govt_pin_mismatch"] == 2
    assert summary["campus_dispersion"] == 1
    assert summary["field_verify"] == 3
    assert summary["stationary_facilities"] == 2
    assert summary["bssid_spatial_splits"] == 1
    assert summary["strategy_agreement_pct"] == pytest.approx(66.7)
    assert summary["commuter_device_facilities"] == 1
    assert summary["coherence_penalised"] == 1
    assert sum(summary[f"confidence_{level}"] for level in ("high", "medium", "low")) == 3
    assert sum(
        summary[key] for key in ("attribution_consistent", "other_entity_nearby", "attribution_unresolved")
    ) == 3

    mobility = validator.mobility_analyzer.analyze_device_mobility("DEV_C")
    assert mobility["reference_source"] == "facility_anchor"


def test_plots_render():
    validator = FacilityValidator(telemetry_df=pd.concat([example_a(), example_c()], ignore_index=True))
    for school in ("SCH_A", "SCH_C"):
        assert validator.plot_facility_map(school, geofence_radius_m=200).data
        assert validator.plot_facility_evidence_timeline(school).data
        assert validator.plot_score_breakdown(school).data
    assert validator.plot_location_triage().data
    assert validator.plot_flag_confidence_breakdown().data
    assert validator.plot_stationary_facility_percentage().data
    profiler = validator.spatial_profiler
    assert profiler.plot_accuracy_ecdf().data
    assert profiler.plot_daily_coverage().data
    assert profiler.build_bssid_profiles() is profiler.build_bssid_profiles()

    events = validator.facility_event_table("SCH_C")
    assert events["in_anchor_window"].any()
    assert set(validator.facility_cluster_table("SCH_C")["school_id_giga"]) == {"SCH_C"}
