"""
GigaMeter spatial research dashboard.

Visualises the multi-track facility audit for research review: ledger
governance, the national audit, single facilities, and single devices. One
cached `FacilityValidator` per country and configuration feeds every tab, and
only the open tab is rendered.

Ledgers are read from `data/spatial_confidence_ledger/{ISO3}/`, one CSV or
Parquet export of `sql/fetch_spatial_confidence_ledger.sql` per country,
already merged with official pins and local time. Set `GIGAMETER_LEDGER_DIR`
to read another folder and `GIGAMETER_LIVE_PINS=0` to start with ledger pins.
"""

import os
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd
import streamlit as st

from src.spatial_intelligence.config import DEFAULT_CONFIG, KNOWN_STRATEGIES, SpatialConfig
from src.spatial_intelligence.facility_validator import FacilityValidator
from src.utils.data_loader import TelemetryLoader, _delta_store_or_default, prepare_schools_frame
from tabs.common import DOCS, TAB_AUDIT, TAB_DEVICE, TAB_FACILITY, TAB_GOVERNANCE, TAB_KEY
from tabs.tab_01_governance import render_tab_governance
from tabs.tab_02_national_audit import render_tab_national_audit
from tabs.tab_03_facility_truth import render_tab_facility_truth
from tabs.tab_04_device_mobility import render_tab_device_mobility

LEDGER_DIR = Path(os.environ.get("GIGAMETER_LEDGER_DIR", "data/spatial_confidence_ledger"))
LIVE_PINS_DEFAULT = os.environ.get("GIGAMETER_LIVE_PINS", "1") != "0"

# Settings exposed in the Advanced panel: (label, step, help).
OVERRIDE_FIELDS = {
    "min_support_device_days": ("Minimum support (device-days)", 1, "Device-days a cluster needs to be supported."),
    "burst_window_s": ("Fix-event burst window (s)", 60.0, "Gap that starts a new fix event."),
    "device_eps_m": ("Device DBSCAN radius (m)", 25.0, "Neighbourhood radius for device clusters."),
    "anchor_eps_m": ("Facility DBSCAN radius (m)", 25.0, "Neighbourhood radius for facility clusters."),
    "govt_anchor_radius_m": ("Official-pin search radius (m)", 250.0, "Govt-proximity strategy radius."),
    "verified_max_m": ("Verified up to (m)", 25.0, "Track 1 VERIFIED distance band."),
    "mismatch_min_m": ("Mismatch from (m)", 50.0, "Track 1 MISMATCH distance band."),
    "other_entity_radius_m": ("Other-entity radius (m)", 25.0, "Track 3 nearby-entity radius."),
}
OVERRIDES_KEY = "config_overrides"

st.set_page_config(
    page_title="GigaMeter spatial research",
    page_icon=":material/satellite_alt:",
    layout="wide",
    initial_sidebar_state="expanded",
)


# -------------------------------------------------------------------
# Cached data and engines
# -------------------------------------------------------------------
@st.cache_data(ttl="10m", show_spinner=False)
def discover_ledgers(root: str) -> Dict[str, Tuple[str, float]]:
    """Newest `.csv` or `.parquet` ledger per country folder, with its mtime."""
    ledgers = {}
    root_path = Path(root)
    if not root_path.is_dir():
        return ledgers
    for folder in sorted(p for p in root_path.iterdir() if p.is_dir()):
        files = [f for f in folder.iterdir() if f.suffix in (".csv", ".parquet")]
        if files:
            newest = max(files, key=lambda f: f.stat().st_mtime)
            ledgers[folder.name.upper()] = (str(newest), newest.stat().st_mtime)
    return ledgers


@st.cache_data(show_spinner="Loading ledger...", max_entries=4)
def load_ledger(path: str, mtime: float) -> pd.DataFrame:
    return TelemetryLoader().load(file_path=path)


@st.cache_data(ttl="6h", show_spinner="Loading official pins from Delta Sharing...", max_entries=8)
def load_live_pins(iso3: str) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """Raw Delta Sharing schools table, checked against the pins contract."""
    try:
        table = _delta_store_or_default(None).load_table(iso3)
        prepare_schools_frame(table)
    except Exception as exc:  # noqa: BLE001 - shown to the user, then falls back
        return None, f"{type(exc).__name__}: {exc}"
    keep = [c for c in ("giga_id_school", "school_id_giga", "latitude", "longitude") if c in table.columns]
    return table[keep], None


@st.cache_resource(show_spinner="Running the facility audit...", max_entries=4, ttl="6h")
def build_engine(
    path: str, mtime: float, iso3: str, overrides: Tuple[Tuple[str, Any], ...], live_pins: bool
) -> Dict[str, Any]:
    """Validator, audit, and pins status for one ledger, configuration, and pins mode."""
    started = time.perf_counter()
    df = load_ledger(path, mtime)
    config = DEFAULT_CONFIG.with_overrides(**dict(overrides))
    pins, pins_error = load_live_pins(iso3) if live_pins else (None, None)
    validator = FacilityValidator(telemetry_df=df, config=config, entity_pins=pins)
    validator.run_national_facility_audit()
    return {
        "validator": validator,
        "pins_label": (
            f"Delta Sharing, live ({len(validator.entity_pins):,} pins)"
            if pins is not None
            else f"Ledger pins ({len(validator.entity_pins):,} pins)"
        ),
        "pins_error": pins_error,
        "build_s": time.perf_counter() - started,
    }


# -------------------------------------------------------------------
# Sidebar
# -------------------------------------------------------------------
def _overrides_panel() -> Tuple[Tuple[str, Any], ...]:
    overrides: Dict[str, Any] = st.session_state.setdefault(OVERRIDES_KEY, {})
    with st.expander("Advanced: calibration overrides", icon=":material/tune:", expanded=bool(overrides)):
        st.caption(
            f"Override v{DEFAULT_CONFIG.methodology_version} settings for this session to test a "
            f"calibration idea. See the [parameter reference]({DOCS['parameters']})."
        )
        with st.form("overrides_form", border=False):
            values: Dict[str, Any] = {}
            for name, (label, step, help_text) in OVERRIDE_FIELDS.items():
                default = getattr(DEFAULT_CONFIG, name)
                values[name] = st.number_input(
                    label,
                    value=overrides.get(name, default),
                    min_value=type(default)(0),
                    step=type(default)(step),
                    help=f"{help_text} Default {default:g}.",
                )
            values["strategies"] = tuple(
                st.multiselect(
                    "Anchor strategies",
                    options=list(KNOWN_STRATEGIES),
                    default=list(overrides.get("strategies", DEFAULT_CONFIG.strategies)),
                    help=f"Default: {', '.join(DEFAULT_CONFIG.strategies)}.",
                )
            )
            apply_col, reset_col = st.columns(2)
            applied = apply_col.form_submit_button("Apply", type="primary", width="stretch")
            reset = reset_col.form_submit_button("Reset", width="stretch")
        if applied:
            changed = {k: v for k, v in values.items() if v != getattr(DEFAULT_CONFIG, k)}
            try:
                DEFAULT_CONFIG.with_overrides(**changed)
            except ValueError as exc:
                st.error(str(exc), icon=":material/error:")
            else:
                st.session_state[OVERRIDES_KEY] = overrides = changed
                st.rerun()
        if reset:
            st.session_state[OVERRIDES_KEY] = {}
            st.rerun()
    return tuple(sorted(overrides.items()))


def _dataset_panel(df: pd.DataFrame, path: str, engine: Dict[str, Any]) -> None:
    with st.container(border=True):
        st.markdown("**Dataset**")
        dates = df["local_date"].dropna()
        st.markdown(
            f"{len(df):,} rows · {df['school_id_giga'].nunique():,} facilities · "
            f"{df['device_id'].nunique():,} devices  \n"
            f"{dates.min()} to {dates.max()} (local dates)"
        )
        if "app_version" in df.columns:
            versions = df["app_version"].value_counts(normalize=True).head(3)
            st.caption(
                "App versions: " + ", ".join(f"{v} ({share:.0%})" for v, share in versions.items())
            )
        st.caption(f"Official pins: {engine['pins_label']}")
        st.caption(
            "Only rows with Google Wi-Fi coordinates are in the ledger; IP coordinates are never used."
        )
        st.caption(f"`{Path(path).name}` · audit built in {engine['build_s']:.1f} s")


ledgers = discover_ledgers(str(LEDGER_DIR))

with st.sidebar:
    st.header("GigaMeter spatial research")
    if not ledgers:
        st.error(f"No ledgers found under `{LEDGER_DIR}/{{ISO3}}/`.", icon=":material/folder_off:")
        st.stop()
    country = st.selectbox("Country", options=list(ledgers), help="Folders found under the ledger directory.")
    live_pins = st.toggle(
        "Live official pins",
        value=LIVE_PINS_DEFAULT,
        help=(
            "Load every official pin of the country from Delta Sharing for Track 3. "
            "Off uses only pins of facilities present in the ledger."
        ),
    )
    geofence_radius = st.slider(
        "Device geofence radius (m)",
        min_value=50,
        max_value=1000,
        value=int(DEFAULT_CONFIG.geofence_radius_m),
        step=25,
        help=f"Device mobility audit only; does not change facility flags. [Geofence audit]({DOCS['geofence']})",
    )
    overrides = _overrides_panel()

path, mtime = ledgers[country]
try:
    engine = build_engine(path, mtime, country, overrides, live_pins)
except Exception as exc:  # noqa: BLE001 - surfaced in the page
    st.error(f"Could not build the audit for {country}: {type(exc).__name__}: {exc}", icon=":material/error:")
    st.exception(exc)
    st.stop()

validator: FacilityValidator = engine["validator"]
validator.mobility_analyzer.set_geofence_radius(geofence_radius)
df_telemetry = validator.spatial_profiler.df

with st.sidebar:
    _dataset_panel(df_telemetry, path, engine)

if engine["pins_error"]:
    st.warning(
        f"Live pins unavailable, using ledger pins for Track 3. {engine['pins_error']}",
        icon=":material/cloud_off:",
    )

# -------------------------------------------------------------------
# Header and tabs
# -------------------------------------------------------------------
config: SpatialConfig = validator.config
with st.container(horizontal=True, vertical_alignment="center"):
    st.title(f"{country} spatial audit", anchor=False)
    st.space("stretch")
    st.markdown(
        f":blue-badge[Methodology v{config.methodology_version}] "
        + (f":orange-badge[Custom config `{config.config_hash}`]" if overrides else f":gray-badge[Config `{config.config_hash}`]")
        + f" [Blueprint]({DOCS['blueprint']})"
    )
if overrides:
    st.caption("Overrides: " + ", ".join(f"`{k}` = {v}" for k, v in overrides))

tab_labels = [TAB_GOVERNANCE, TAB_AUDIT, TAB_FACILITY, TAB_DEVICE]
tabs = st.tabs(tab_labels, key=TAB_KEY, on_change="rerun")
renderers = [
    lambda: render_tab_governance(validator),
    lambda: render_tab_national_audit(validator),
    lambda: render_tab_facility_truth(validator, geofence_radius),
    lambda: render_tab_device_mobility(validator),
]
for tab, render in zip(tabs, renderers):
    with tab:
        if tab.open:
            render()
