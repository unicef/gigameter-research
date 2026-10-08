"""
Module: tabs/common.py
Purpose: Shared labels, colours, documentation links and table formats for
         the dashboard tabs.
"""

from typing import Iterable, Optional

import pandas as pd
import streamlit as st

DOCS_BASE = "https://unicef.github.io/gigameter-research/latest/"
DOCS = {
    "blueprint": DOCS_BASE + "blueprint/technical_blueprint/",
    "parameters": DOCS_BASE + "blueprint/parameters/",
    "fix_events": DOCS_BASE + "blueprint/technical_blueprint/#2-evidence-unit-fix-events",
    "mobility": DOCS_BASE + "blueprint/technical_blueprint/#42-classification-rules",
    "geofence": DOCS_BASE + "blueprint/technical_blueprint/#43-geofence-audit",
    "hotspots": DOCS_BASE + "blueprint/technical_blueprint/#52-hotspot-bssid-mobility-signals",
    "clusters": DOCS_BASE + "blueprint/technical_blueprint/#53-facility-observation-clusters",
    "strategies": DOCS_BASE + "blueprint/technical_blueprint/#54-strategy-candidates-agreement",
    "raw_score": DOCS_BASE + "blueprint/technical_blueprint/#61-raw-score-s_raw",
    "track1": DOCS_BASE + "blueprint/technical_blueprint/#62-track-1-location-truth",
    "track2": DOCS_BASE + "blueprint/technical_blueprint/#63-track-2-hardware-integrity",
    "track3": DOCS_BASE + "blueprint/technical_blueprint/#64-track-3-entity-attribution",
}

# Streamlit badge colours per category, matching src/spatial_intelligence/palette.py.
FLAG_BADGE = {
    "VERIFIED_ACCURATE": "green",
    "CAMPUS_DISPERSION": "orange",
    "GOVT_PIN_MISMATCH": "red",
    "AMBIGUOUS_MULTI_CLUSTER": "violet",
    "UNSTABLE_MOBILE_ONLY": "orange",
    "NO_GOVT_PIN_AVAILABLE": "gray",
    "INSUFFICIENT_DATA": "gray",
}
ACTION_BADGE = {"SUBMIT_CORRECTION": "red", "FIELD_VERIFY": "orange", "AWAIT_DATA": "gray", "NONE": "green"}
CONFIDENCE_BADGE = {"HIGH": "green", "MEDIUM": "orange", "LOW": "red"}
MOBILITY_BADGE = {
    "STATIONARY": "green",
    "COMMUTER": "blue",
    "RELOCATED": "orange",
    "HIGH_MOBILITY": "red",
    "INSUFFICIENT_EVIDENCE": "gray",
}
ATTRIBUTION_BADGE = {"CONSISTENT": "green", "OTHER_ENTITY_NEARBY": "red", "UNRESOLVED": "gray"}

FLAG_LABELS = {
    "VERIFIED_ACCURATE": "Verified",
    "CAMPUS_DISPERSION": "Campus dispersion",
    "GOVT_PIN_MISMATCH": "Pin mismatch",
    "AMBIGUOUS_MULTI_CLUSTER": "Ambiguous",
    "UNSTABLE_MOBILE_ONLY": "Unstable",
    "NO_GOVT_PIN_AVAILABLE": "No official pin",
    "INSUFFICIENT_DATA": "Insufficient data",
}
ACTION_LABELS = {
    "SUBMIT_CORRECTION": "Submit correction",
    "FIELD_VERIFY": "Field verify",
    "AWAIT_DATA": "Await data",
    "NONE": "No action",
}
TAG_LABELS = {
    "BSSID_SPATIAL_SPLIT": "BSSID spatial split",
    "HOTSPOT_TETHERED_FACILITY": "Hotspot-tethered facility",
    "COMMUTER_DEVICE": "Commuter device in anchor",
    "RELOCATED_DEVICE": "Relocated device",
}

TAB_GOVERNANCE = ":material/fact_check: Ledger governance"
TAB_AUDIT = ":material/public: National audit"
TAB_FACILITY = ":material/location_on: Facility inspector"
TAB_DEVICE = ":material/devices: Device mobility"
TAB_KEY = "main_tab"
FACILITY_KEY = "selected_school"
DEVICE_SCHOOL_KEY = "device_school"
DEVICE_KEY = "selected_device"


def badge(value: Optional[str], colors: dict, labels: Optional[dict] = None) -> str:
    """Markdown badge for a methodology category."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ":gray-badge[n/a]"
    text = (labels or {}).get(value, str(value).replace("_", " ").capitalize())
    return f":{colors.get(value, 'gray')}-badge[{text}]"


def facility_label(school_id: str, names: dict) -> str:
    name = names.get(school_id)
    return f"{name} ({school_id})" if name and name != school_id else str(school_id)


def fmt_m(value) -> str:
    return "n/a" if value is None or pd.isna(value) else f"{value:,.0f} m"


def open_facility(school_id: str) -> None:
    """Callback: show a facility in the inspector tab."""
    st.session_state[FACILITY_KEY] = school_id
    st.session_state[TAB_KEY] = TAB_FACILITY


def open_device(school_id: str, device_id: str) -> None:
    """Callback: show a device in the mobility tab."""
    st.session_state[DEVICE_SCHOOL_KEY] = school_id
    st.session_state[DEVICE_KEY] = device_id
    st.session_state[TAB_KEY] = TAB_DEVICE


def selected_row(state_key: str) -> Optional[int]:
    """Row position selected in a keyed `st.dataframe`, if any."""
    state = st.session_state.get(state_key)
    rows = state.selection.rows if state is not None else []
    return rows[0] if rows else None


def join_values(values: Iterable) -> str:
    return ", ".join(str(v) for v in values if v is not None and not (isinstance(v, float) and pd.isna(v)))


def distance_column(label: str, help: Optional[str] = None):
    return st.column_config.NumberColumn(label, help=help, format="%.0f m")


def pct_column(label: str, help: Optional[str] = None):
    return st.column_config.NumberColumn(label, help=help, format="%.1f%%")


def score_column(label: str, help: Optional[str] = None):
    return st.column_config.ProgressColumn(label, help=help, min_value=0, max_value=100, format="%.1f")


def list_column(label: str, help: Optional[str] = None):
    return st.column_config.ListColumn(label, help=help)
