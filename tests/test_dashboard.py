"""Smoke test: every dashboard tab renders on a synthetic ledger."""

from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest  # noqa: E402

from spatial_fixtures import example_a, example_b, example_c
from tabs.common import FACILITY_KEY, TAB_AUDIT, TAB_DEVICE, TAB_FACILITY, TAB_KEY

APP = Path(__file__).resolve().parents[1] / "app.py"


@pytest.fixture
def app(tmp_path, monkeypatch):
    country = tmp_path / "TST"
    country.mkdir()
    ledger = pd.concat([example_a(), example_b(), example_c()], ignore_index=True)
    ledger.to_csv(country / "TST_spatial_confidence_ledger.csv", index=False)
    monkeypatch.setenv("GIGAMETER_LEDGER_DIR", str(tmp_path))
    monkeypatch.setenv("GIGAMETER_LIVE_PINS", "0")
    at = AppTest.from_file(str(APP), default_timeout=120)
    at.run()
    return at


def _assert_clean(at: AppTest) -> None:
    assert not at.exception, [e.message for e in at.exception]
    assert not at.error, [e.value for e in at.error]


def _metric_labels(at: AppTest) -> set:
    return {m.label for m in at.metric}


def test_every_tab_renders(app):
    _assert_clean(app)
    assert any("TST" in t.value for t in app.title)
    assert "Fix events" in _metric_labels(app)

    app.session_state[TAB_KEY] = TAB_AUDIT
    app.run()
    _assert_clean(app)
    assert {"Submit correction", "Strategy agreement", "Other entity nearby"} <= _metric_labels(app)

    app.session_state[FACILITY_KEY] = "SCH_C"
    app.session_state[TAB_KEY] = TAB_FACILITY
    app.run()
    _assert_clean(app)
    assert any("BSSID spatial split" in w.value for w in app.warning)
    assert "Hardware score" in _metric_labels(app)

    app.session_state[TAB_KEY] = TAB_DEVICE
    app.run()
    _assert_clean(app)
    assert {"Evidence days", "Transitions", "Inside geofence"} <= _metric_labels(app)


def _device_metric(at: AppTest, label: str) -> str:
    return next(m.proto.help for m in at.metric if m.label == label)


def test_geofence_slider_only_changes_device_audit(app):
    # AppTest does not send the active tab back, so it is set before each run.
    app.session_state[TAB_KEY] = TAB_DEVICE
    app.run()
    assert "within 200 m" in _device_metric(app, "Inside geofence")
    build = [c.value for c in app.sidebar.caption if "audit built" in c.value]

    app.slider[0].set_value(50)
    app.session_state[TAB_KEY] = TAB_DEVICE
    app.run()
    _assert_clean(app)
    assert "within 50 m" in _device_metric(app, "Inside geofence")
    assert [c.value for c in app.sidebar.caption if "audit built" in c.value] == build
