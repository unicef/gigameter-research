"""
Tab 4: Device Trajectories & Mobility with Cascading Dropdowns.
"""

import streamlit as st
import pandas as pd
from src.spatial_intelligence.mobility_analyzer import MobilityAnalyzer


def render_tab_device_mobility(
    df_telemetry: pd.DataFrame, mobility_engine: MobilityAnalyzer
):
    st.subheader("Pillar 1: Hardware Mobility & Trajectory Inspector")
    st.write(
        "Classifying hardware trajectories using DBSCAN spatial clustering "
        "(Haversine metric) and operational hour window analysis."
    )

    if df_telemetry.empty:
        st.warning("No telemetry data available for mobility inspection.")
        return

    # Cascading Dropdowns: School -> Filtered Devices
    c_col1, c_col2 = st.columns(2)

    with c_col1:
        unique_schools = list(df_telemetry["school_id_giga"].unique())
        selected_school = st.selectbox(
            "1. Select Target School Facility:", options=unique_schools, index=0
        )

    school_telemetry = df_telemetry[df_telemetry["school_id_giga"] == selected_school]
    available_devices = list(school_telemetry["device_id"].unique())

    with c_col2:
        selected_device_id = st.selectbox(
            "2. Select Hardware Device at School:",
            options=available_devices,
            index=0,
        )

    st.markdown("---")

    # -------------------------------------------------------------------
    # Render Device Trajectory Audit
    # -------------------------------------------------------------------
    if selected_device_id:
        mobility_report = mobility_engine.analyze_device_mobility(selected_device_id)

        if "error" not in mobility_report:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Assigned School", mobility_report["school_id_giga"])
            m2.metric("Behavior Classification", mobility_report["mobility_class"])
            m3.metric(
                "Geofence Compliance", f"{mobility_report['compliance_rate_pct']}%"
            )
            m4.metric("DBSCAN Clusters", mobility_report["cluster_count"])

            st.markdown("---")

            st.markdown("#### Device Spatial Cluster Map (DBSCAN)")
            fig_mob_map = mobility_engine.plot_device_mobility_map(selected_device_id)
            st.plotly_chart(fig_mob_map, use_container_width=True)

            st.markdown("---")

            # Phase 1 Visualizations: Displacement Timeline & Time-of-Day Commuter Scatter
            t_col1, t_col2 = st.columns(2)
            with t_col1:
                st.markdown("#### Displacement Timeline")
                fig_timeline = mobility_engine.plot_displacement_timeline(
                    selected_device_id
                )
                st.plotly_chart(fig_timeline, use_container_width=True)

            with t_col2:
                st.markdown("#### Time-of-Day Commuter Pattern")
                fig_tod = mobility_engine.plot_commuter_time_of_day_scatter(
                    selected_device_id
                )
                st.plotly_chart(fig_tod, use_container_width=True)
