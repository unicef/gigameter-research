"""
Streamlit Web Application — GigaMeter Two-Track Spatial Analytics Dashboard
Purpose: Main orchestrator script incorporating local pre-enriched CSV loader,
         graceful missing country error interception, and modular tab package.
Rules: Aligned with GigaMeter Data Dictionary v2.2 (08:00 - 19:59 Operational Window).
"""

import os
import streamlit as st

from src.spatial_intelligence.spatial_profiler import ClusterResolutionStrategy
from src.spatial_intelligence.mobility_analyzer import MobilityAnalyzer
from src.spatial_intelligence.facility_validator import FacilityValidator
from src.utils.data_loader import TelemetryLoader

from tabs.tab_01_governance import render_tab_governance
from tabs.tab_02_national_audit import render_tab_national_audit
from tabs.tab_03_facility_truth import render_tab_facility_truth
from tabs.tab_04_device_mobility import render_tab_device_mobility

# -------------------------------------------------------------------
# 1. PAGE CONFIGURATION
# -------------------------------------------------------------------
st.set_page_config(
    page_title="GigaMeter Two-Track Spatial Dashboard",
    page_icon=":material/stacked_line_chart:",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("GigaMeter Spatial Research & Location Truth Dashboard")
st.caption("Baseline v0.2 - Two-Track Architecture")

# -------------------------------------------------------------------
# 2. SIDEBAR CONTROLS & STRATEGY SELECTION
# -------------------------------------------------------------------
st.sidebar.header("Data & Strategy Controls")

selected_country = st.sidebar.selectbox(
    "Select Target Country (ISO3):",
    options=["MNG", "ALB", "LKA", "UZB"],
    index=0,
    help="Loads pre-enriched ledger from data/spatial_confidence_ledger/{iso3}/",
)

strategy_option = st.sidebar.selectbox(
    "Primary Cluster Selection Strategy",
    options=[
        (
            "Prior-Informed (Govt Proximity Tie-Breaker)",
            ClusterResolutionStrategy.GOVT_PROXIMITY_ANCHOR,
        ),
        (
            "Unbiased (Pure Telemetry Dominance)",
            ClusterResolutionStrategy.TELEMETRY_DOMINANCE,
        ),
        (
            "Hardware-First (Stationary Device Priority)",
            ClusterResolutionStrategy.STATIONARY_FIRST,
        ),
    ],
    format_func=lambda x: x[0],
    help="Determines how candidate BSSID clusters are prioritized when resolving BSSID spatial splits (> 2km).",
)
selected_strategy = strategy_option[1]

geofence_radius = st.sidebar.slider(
    "Geofence Campus Boundary (meters)",
    min_value=50,
    max_value=500,
    value=200,
    step=25,
    help="Allowed campus radius around empirical centroid.",
)

st.sidebar.markdown("---")
st.sidebar.subheader("Dataset Metadata")
st.sidebar.markdown(
    "**Baseline Window:** `2026-01-01` to `2026-08-05`\n\n"
    "**App Version:** `>= 2.0.2` (Active Google API Scanning)\n\n"
    "**Operational Window:** `08:00:00` to `19:59:59` Local Device Time\n\n"
    "**Geolocation Policy:** Strict No-IP Fallback (Null coordinates discarded)"
)


# -------------------------------------------------------------------
# 3. DIRECT LOCAL CSV DATA LOADER PIPELINE
# -------------------------------------------------------------------
@st.cache_data(ttl=3600)
def load_country_telemetry(country_iso3: str):
    """
    Load a pre-enriched spatial confidence ledger CSV through TelemetryLoader.

    Returns None if the file is missing or cannot be read into the canonical
    telemetry contract. Frames that already contain government pins and local
    time skip Delta Sharing and timezone enrichment.
    """
    file_path = f"data/spatial_confidence_ledger/{country_iso3}/{country_iso3}_spatial_confidence_ledger_05-08-2026.csv"

    if not os.path.exists(file_path):
        return None

    try:
        return TelemetryLoader().load(file_path=file_path)
    except Exception:
        return None


# Ingest Data
df_telemetry = load_country_telemetry(selected_country)

# -------------------------------------------------------------------
# 4. ERROR INTERCEPTION
# -------------------------------------------------------------------
if df_telemetry is None or df_telemetry.empty:
    st.warning(
        f"⚠️ Spatial confidence ledger dataset for country **[{selected_country}]** "
        f"is not available in local storage (`data/spatial_confidence_ledger/{selected_country}/`)."
    )
    st.info(
        "Please extract the country dataset or select a supported ISO3 code from the sidebar."
    )
    st.stop()

# Initialize Engines
validator = FacilityValidator(
    telemetry_df=df_telemetry,
    geofence_radius_m=geofence_radius,
    strategy=selected_strategy,
)

mobility_engine = MobilityAnalyzer(
    telemetry_df=df_telemetry,
    geofence_radius_m=geofence_radius,
    strategy=selected_strategy,
)

# -------------------------------------------------------------------
# 5. TAB RENDERING
# -------------------------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs(
    [
        "Telemetry Governance & Ledger",
        "Two-Track National Audit",
        "Facility Location Inspector",
        "Device Mobility & Trajectories",
    ]
)

with tab1:
    render_tab_governance(df_telemetry)

with tab2:
    render_tab_national_audit(selected_country, validator, mobility_engine)

with tab3:
    render_tab_facility_truth(validator)

with tab4:
    render_tab_device_mobility(df_telemetry, mobility_engine)
