"""
Tab 1: ledger governance.

Shows what evidence the ledger holds before any methodology choice: rows,
fix events, carried rows, accuracy, operational-hours share, hotspot signals,
and daily coverage. Uses the validator's own `SpatialProfiler`.
"""

import plotly.express as px
import streamlit as st

from src.spatial_intelligence.facility_validator import FacilityValidator
from tabs.common import DOCS, distance_column

LEDGER_COLUMNS = {
    "school_id_giga": st.column_config.TextColumn("Facility ID"),
    "school_name": st.column_config.TextColumn("Facility"),
    "device_id": st.column_config.TextColumn("Device"),
    "local_created_timestamp": st.column_config.DatetimeColumn("Local time", format="YYYY-MM-DD HH:mm"),
    "detected_wifi_ssid": st.column_config.TextColumn("SSID"),
    "detected_wifi_bssid": st.column_config.TextColumn("BSSID"),
    "detected_latitude": st.column_config.NumberColumn("Latitude", format="%.5f"),
    "detected_longitude": st.column_config.NumberColumn("Longitude", format="%.5f"),
    "detected_location_accuracy": distance_column("Accuracy"),
    "wifi_signal_dbm": st.column_config.NumberColumn("Signal", format="%d dBm"),
    "is_operational_hours": st.column_config.CheckboxColumn("Operational hours"),
    "is_hotspot_ssid": st.column_config.CheckboxColumn("Hotspot SSID"),
    "is_mobile_bssid": st.column_config.CheckboxColumn("Moving router"),
    "app_version": st.column_config.TextColumn("App version"),
}


def render_tab_governance(validator: FacilityValidator) -> None:
    profiler = validator.spatial_profiler
    gov = profiler.summarize_governance()
    df = profiler.df

    st.caption(
        "The ledger holds only rows where the Google Wi-Fi lookup returned coordinates, so the lookup "
        f"success rate cannot be measured here. Evidence is counted in [fix events]({DOCS['fix_events']}): "
        "consecutive rows with the same coordinates and network collapse into one."
    )

    with st.container(horizontal=True):
        st.metric("Ledger rows", f"{gov['total_records']:,}", border=True)
        st.metric(
            "Fix events",
            f"{gov['total_fix_events']:,}",
            help="Independent location observations after collapsing repeated rows.",
            border=True,
        )
        st.metric(
            "Carried rows",
            f"{gov['carried_pct']}%",
            help="Rows that repeat a fix under a different network than the one that produced it.",
            border=True,
        )
        st.metric("Facilities", f"{gov['facilities']:,}", border=True)
        st.metric("Devices", f"{gov['devices']:,}", border=True)

    with st.container(horizontal=True):
        st.metric(
            "Median accuracy",
            f"{gov['median_accuracy_m']:,.0f} m",
            help=f"Google accuracy radius. Mean {gov['mean_accuracy_m']:,.0f} m.",
            border=True,
        )
        st.metric(
            "Operational hours",
            f"{gov['operational_hours_pct']}%",
            help="Rows inside 08:00-19:59 local device time.",
            border=True,
        )
        st.metric(
            "No associated Wi-Fi",
            f"{gov['ambient_pct']}%",
            help="Rows without a connected BSSID (wired, or not associated). Coordinates still come from nearby access points.",
            border=True,
        )
        st.metric(
            "Hotspot SSID",
            f"{gov['hotspot_ssid_pct']}%",
            help="Rows whose SSID matches the phone-hotspot pattern.",
            border=True,
        )
        st.metric(
            "Moving router",
            f"{gov['mobile_bssid_pct']}%",
            help=f"Rows on a BSSID seen at two or more places on separate days ({gov['mobile_bssids']} BSSIDs). [Hotspot signals]({DOCS['hotspots']})",
            border=True,
        )

    left, right = st.columns(2)
    with left.container(border=True):
        st.markdown("**Accuracy radius distribution**")
        st.plotly_chart(profiler.plot_accuracy_ecdf(), width="stretch")
    with right.container(border=True):
        st.markdown("**Daily coverage**")
        st.plotly_chart(profiler.plot_daily_coverage(), width="stretch")

    left, right = st.columns(2)
    with left.container(border=True):
        st.markdown("**Rows by local hour**")
        if "local_hour" in df.columns:
            hourly = (
                df.groupby(["local_hour", "is_operational_hours"]).size().reset_index(name="rows")
            )
            fig = px.bar(
                hourly,
                x="local_hour",
                y="rows",
                color="is_operational_hours",
                color_discrete_map={True: "#2e7d32", False: "#c62828"},
                labels={"local_hour": "Local hour", "rows": "Rows", "is_operational_hours": "Operational hours"},
                height=380,
            )
            fig.update_layout(template="plotly_white", margin=dict(l=10, r=10, t=10, b=30))
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("No local time in this ledger.")
    with right.container(border=True):
        st.markdown("**Signal strength against accuracy**")
        st.plotly_chart(profiler.plot_signal_vs_accuracy_density(), width="stretch")

    rows = st.expander("Ledger rows", icon=":material/table:", key="ledger_rows", on_change="rerun")
    with rows:
        if not rows.open:
            return
        columns = [c for c in LEDGER_COLUMNS if c in df.columns]
        st.dataframe(
            df[columns],
            column_config=LEDGER_COLUMNS,
            hide_index=True,
            width="stretch",
            height=420,
        )
