"""
Tab 1: Telemetry Governance, API Precision & Quality Ledger.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from src.spatial_intelligence.spatial_profiler import SpatialProfiler


def render_tab_governance(df_telemetry: pd.DataFrame):
    st.subheader("Telemetry Governance & Quality Ledger")
    st.write(
        "Auditing raw telemetry quality, active Google Geolocation API precision distributions, "
        "and operational hour compliance (08:00–19:59 local time)."
    )

    profiler = SpatialProfiler(df_telemetry)
    governance = profiler.summarize_governance()

    # -------------------------------------------------------------------
    # 1. Quality & Contamination Metric Cards
    # -------------------------------------------------------------------
    q1, q2, q3, q4, q5 = st.columns(5)
    q1.metric("Total Measurement Records", f"{governance['total_records']:,}")
    q2.metric(
        "Hotspot Contamination Share",
        f"{governance['hotspot_pct']}% ({governance['hotspot_scans']:,})",
        delta_color="inverse",
    )
    q3.metric(
        "Ambient Scans (Null BSSID)",
        f"{governance['ambient_scans']:,} ({governance['ambient_pct']}%)",
    )
    q4.metric("Mean API Precision Radius", f"{governance['mean_accuracy_m']}m")
    q5.metric(
        "Active Operational Hours Share",
        f"{governance['operational_hours_pct']}%",
    )

    st.markdown("---")

    # -------------------------------------------------------------------
    # 2. Data Quality Distributions
    # -------------------------------------------------------------------
    q_col1, q_col2 = st.columns(2)

    with q_col1:
        st.markdown("##### Google Geolocation API Precision Distribution")
        if "detected_location_accuracy" in df_telemetry.columns:
            fig_acc = px.histogram(
                df_telemetry,
                x="detected_location_accuracy",
                nbins=30,
                color_discrete_sequence=["#277aff"],
                labels={
                    "detected_location_accuracy": "Accuracy Radius (m)",
                    "count": "Record Count",
                },
            )
            fig_acc.update_layout(template="plotly_white", height=320)
            st.plotly_chart(fig_acc, use_container_width=True)

    with q_col2:
        st.markdown("##### Operational Window Distribution (08:00-19:59 Local Time)")
        if "local_hour" in df_telemetry.columns:
            fig_hour = px.histogram(
                df_telemetry,
                x="local_hour",
                nbins=24,
                color="is_operational_hours",
                color_discrete_map={True: "#2ca02c", False: "#d62728"},
                labels={
                    "local_hour": "Local Hour of Day (0-23)",
                    "is_operational_hours": "08:00-19:59 Window",
                },
            )
            fig_hour.update_layout(template="plotly_white", height=320)
            st.plotly_chart(fig_hour, use_container_width=True)

    st.markdown("---")

    # -------------------------------------------------------------------
    # 3. Signal Strength vs Precision
    # -------------------------------------------------------------------
    st.markdown("##### Wi-Fi Signal Strength (dBm) vs Geolocation API Precision Radius")
    try:
        fig_signal = profiler.plot_signal_vs_accuracy_density()
        st.plotly_chart(fig_signal, use_container_width=True)
    except Exception as e:
        st.warning(f"Could not render signal density plot: {e}")

    st.markdown("---")

    # -------------------------------------------------------------------
    # 4. Raw Pre-Enriched Data Explorer
    # -------------------------------------------------------------------
    st.markdown("##### Pre-Enriched Telemetry Ledger Viewer")
    st.dataframe(df_telemetry, use_container_width=True)
