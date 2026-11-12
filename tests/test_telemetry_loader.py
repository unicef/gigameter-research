"""Contract tests for TelemetryLoader. No live database or Delta share."""

from pathlib import Path

import pandas as pd
import pytest

from src.utils.data_loader import (
    LOCAL_TIME_COLUMNS,
    TelemetryLoader,
    canonicalize_telemetry_columns,
)


def _local_time_fields() -> dict:
    return {
        "tz_name": "Europe/Tirane",
        "local_created_timestamp": "2026-01-01 09:00:00",
        "local_date": "2026-01-01",
        "local_hour": 9,
        "local_day_of_week": "Thursday",
        "is_weekday": True,
        "is_operational_hours": True,
    }


def _telemetry_row(**overrides) -> dict:
    row = {
        "school_id_giga": "S1",
        "device_id": "D1",
        "detected_latitude": 41.0,
        "detected_longitude": 19.0,
        "created_timestamp": "2026-01-01T08:00:00Z",
    }
    row.update(_local_time_fields())
    row.update(overrides)
    return row


def _telemetry(**overrides) -> pd.DataFrame:
    return pd.DataFrame([_telemetry_row(**overrides)])


class FakeDB:
    def __init__(self, ok: bool = True, frame: pd.DataFrame | None = None) -> None:
        self.ok = ok
        self.frame = frame if frame is not None else pd.DataFrame()
        self.tested = False
        self.queries: list[str] = []

    def test_connection(self) -> bool:
        self.tested = True
        return self.ok

    def read_sql_to_dataframe(self, query: str, params=None) -> pd.DataFrame:
        self.queries.append(query)
        return self.frame.copy()


class FakeDelta:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame
        self.calls: list[str] = []

    def load_table(self, table_name: str) -> pd.DataFrame:
        self.calls.append(table_name)
        return self.frame.copy()


def test_canonicalize_renames_aliases_once() -> None:
    frame = pd.DataFrame(
        [
            {
                "giga_id_school": "S1",
                "device_hardware_id": "D1",
                "detected_bssid": "aa:bb",
                "detected_ssid": "SchoolWiFi",
                "detected_wifi_signal": -40,
                "is_school_hours": True,
                "latitude": 41.2,
                "longitude": 19.2,
            }
        ]
    )

    canonical = canonicalize_telemetry_columns(frame)

    assert list(canonical["school_id_giga"]) == ["S1"]
    assert list(canonical["device_id"]) == ["D1"]
    assert list(canonical["detected_wifi_bssid"]) == ["aa:bb"]
    assert list(canonical["detected_wifi_ssid"]) == ["SchoolWiFi"]
    assert list(canonical["wifi_signal_dbm"]) == [-40]
    assert list(canonical["is_operational_hours"]) == [True]
    assert list(canonical["govt_latitude"]) == [41.2]
    assert list(canonical["govt_longitude"]) == [19.2]
    assert "giga_id_school" not in canonical.columns
    assert "is_school_hours" not in canonical.columns
    assert "latitude" not in canonical.columns


def test_operational_hours_alias_is_kept_when_canonical_flag_exists() -> None:
    frame = pd.DataFrame(
        [{"is_school_hours": False, "is_operational_hours": True}]
    )

    canonical = canonicalize_telemetry_columns(frame)

    assert list(canonical["is_operational_hours"]) == [True]
    assert list(canonical["is_school_hours"]) == [False]


def test_rejects_zero_or_two_sources() -> None:
    db = FakeDB()
    with pytest.raises(ValueError, match="exactly one"):
        TelemetryLoader().load()
    with pytest.raises(ValueError, match="exactly one"):
        TelemetryLoader().load(
            telemetry_df=_telemetry(),
            file_path="ledger.csv",
            db=db,
        )
    assert db.tested is False


def test_schools_df_merge_does_not_call_delta() -> None:
    delta = FakeDelta(
        pd.DataFrame(
            {"school_id_giga": ["S1"], "latitude": [0.0], "longitude": [0.0]}
        )
    )
    schools = pd.DataFrame(
        {
            "giga_id_school": ["S1", "S1"],
            "latitude": [41.3, 41.3],
            "longitude": [19.3, 19.3],
            "school_name": ["One", "One"],
        }
    )
    telemetry = pd.DataFrame(
        [
            _telemetry_row(school_id_giga="S1"),
            _telemetry_row(school_id_giga="S2", device_id="D2"),
        ]
    )

    loaded = TelemetryLoader().load(
        telemetry_df=telemetry,
        schools_df=schools,
        delta_store=delta,
    )

    assert delta.calls == []
    assert loaded.loc[loaded["school_id_giga"] == "S1", "govt_latitude"].iloc[0] == 41.3
    assert pd.isna(
        loaded.loc[loaded["school_id_giga"] == "S2", "govt_latitude"].iloc[0]
    )
    assert "school_name" not in loaded.columns


def test_delta_load_when_schools_df_omitted() -> None:
    delta = FakeDelta(
        pd.DataFrame(
            {
                "school_id_giga": ["S1"],
                "latitude": [41.4],
                "longitude": [19.4],
            }
        )
    )

    loaded = TelemetryLoader().load(
        telemetry_df=_telemetry(),
        country_iso3="XXX",
        delta_store=delta,
    )

    assert delta.calls == ["XXX"]
    assert loaded["govt_latitude"].iloc[0] == 41.4
    assert loaded["govt_longitude"].iloc[0] == 19.4


def test_existing_govt_pins_skip_delta_on_query_path() -> None:
    delta = FakeDelta(
        pd.DataFrame(
            {"school_id_giga": ["S1"], "latitude": [41.5], "longitude": [19.5]}
        )
    )
    db = FakeDB(
        frame=_telemetry(govt_latitude=41.7, govt_longitude=19.7)
    )

    loaded = TelemetryLoader().load(
        query_name="fetch_spatial_confidence_ledger",
        query_params={
            "country_iso3": "XXX",
            "start_date": "2026-01-01",
            "end_date": "2026-08-05",
            "min_app_version": "2.0.2",
        },
        db=db,
        delta_store=delta,
    )

    assert db.tested is True
    assert "XXX" in db.queries[0]
    assert delta.calls == []
    assert loaded["govt_latitude"].iloc[0] == pytest.approx(41.7)


def test_latitude_alias_on_telemetry_skips_delta() -> None:
    delta = FakeDelta(
        pd.DataFrame(
            {"school_id_giga": ["S1"], "latitude": [0.0], "longitude": [0.0]}
        )
    )

    loaded = TelemetryLoader().load(
        telemetry_df=_telemetry(latitude=41.9, longitude=19.9),
        country_iso3="XXX",
        delta_store=delta,
    )

    assert delta.calls == []
    assert loaded["govt_latitude"].iloc[0] == pytest.approx(41.9)
    assert "latitude" not in loaded.columns


def test_query_without_pins_uses_country_from_params() -> None:
    raw = _telemetry().drop(columns=["govt_latitude"], errors="ignore")
    delta = FakeDelta(
        pd.DataFrame(
            {"school_id_giga": ["S1"], "latitude": [41.6], "longitude": [19.6]}
        )
    )
    db = FakeDB(frame=raw)

    loaded = TelemetryLoader().load(
        query_name="fetch_spatial_confidence_ledger",
        query_params={
            "country_iso3": "XXX",
            "start_date": "2026-01-01",
            "end_date": "2026-08-05",
            "min_app_version": "2.0.2",
        },
        db=db,
        delta_store=delta,
    )

    assert delta.calls == ["XXX"]
    assert loaded["govt_latitude"].iloc[0] == 41.6


def test_skips_clients_when_frame_is_already_enriched() -> None:
    loaded = TelemetryLoader().load(
        telemetry_df=_telemetry(govt_latitude=41.7, govt_longitude=19.7)
    )

    assert loaded["govt_latitude"].iloc[0] == 41.7
    for column in LOCAL_TIME_COLUMNS:
        assert column in loaded.columns


def test_test_connection_failure_raises_before_query() -> None:
    db = FakeDB(ok=False)

    with pytest.raises(ConnectionError, match="connection test failed"):
        TelemetryLoader().load(
            query_name="fetch_spatial_confidence_ledger",
            query_params={"country_iso3": "XXX"},
            db=db,
        )

    assert db.tested is True
    assert db.queries == []


def test_schools_frame_requires_latitude_and_longitude() -> None:
    schools = pd.DataFrame({"school_id_giga": ["S1"], "latitude": [41.0]})

    with pytest.raises(ValueError, match="longitude"):
        TelemetryLoader().load(
            telemetry_df=_telemetry(),
            schools_df=schools,
        )


def test_reads_csv_ledger(tmp_path: Path) -> None:
    path = tmp_path / "XXX_spatial_confidence_ledger.csv"
    _telemetry(govt_latitude=41.8, govt_longitude=19.8).to_csv(path, index=False)

    loaded = TelemetryLoader().load(file_path=path)

    assert loaded["school_id_giga"].iloc[0] == "S1"
    assert loaded["govt_latitude"].iloc[0] == pytest.approx(41.8)


def test_summarize_governance_counts_ambient_and_hotspot_rows() -> None:
    from src.spatial_intelligence.spatial_profiler import SpatialProfiler

    frame = pd.DataFrame(
        [
            _telemetry_row(
                device_id="D1",
                detected_wifi_bssid=None,
                detected_wifi_ssid=None,
                detected_location_accuracy=10.0,
                is_operational_hours=True,
                govt_latitude=41.33,
                govt_longitude=19.82,
            ),
            _telemetry_row(
                device_id="D2",
                detected_wifi_bssid="aa:bb:cc:dd:ee:ff",
                detected_wifi_ssid="iPhone",
                detected_location_accuracy=30.0,
                is_operational_hours=False,
                govt_latitude=41.33,
                govt_longitude=19.82,
            ),
        ]
    )

    summary = SpatialProfiler(frame).summarize_governance()

    assert summary["total_records"] == 2
    assert summary["ambient_scans"] == 1
    assert summary["ambient_pct"] == 50.0
    assert summary["hotspot_scans"] == 1
    assert summary["hotspot_pct"] == 50.0
    assert summary["mean_accuracy_m"] == 20.0
    assert summary["operational_hours_pct"] == 50.0


def test_facility_validator_reuses_spatial_summary() -> None:
    from src.spatial_intelligence.facility_validator import FacilityValidator

    validator = FacilityValidator(
        telemetry_df=_telemetry(
            govt_latitude=41.33,
            govt_longitude=19.82,
            detected_wifi_bssid="aa:bb:cc:dd:ee:ff",
            detected_location_accuracy=20.0,
            school_name="School One",
        )
    )

    assert validator.mobility_analyzer.profiler is None
    assert validator.mobility_analyzer.facility_summary is validator.facility_summary
    assert validator.facility_summary["school_id_giga"].iloc[0] == "S1"

    audit_summary = validator.summarize_national_audit()
    assert audit_summary["total_facilities"] == 1
    assert audit_summary["stationary_facilities"] == 0
    assert audit_summary["stationary_pct"] == 0.0
    assert audit_summary["verified_accurate"] == 0
    assert audit_summary["govt_pin_mismatch"] == 0
    assert audit_summary["campus_dispersion"] == 0
    assert "bssid_spatial_splits" in audit_summary
    assert "hotspot_tethered_facilities" in audit_summary
    assert "mean_hardware_health_score" in audit_summary


def test_rejects_unsupported_file_suffix(tmp_path: Path) -> None:
    path = tmp_path / "ledger.txt"
    path.write_text("not telemetry")

    with pytest.raises(ValueError, match=".csv or .parquet"):
        TelemetryLoader().load(file_path=path)
