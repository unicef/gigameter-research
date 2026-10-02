"""
Tab 3: Facility Location Truth Inspector & Decoupled Standalone Plot Views.
"""

import streamlit as st
from src.spatial_intelligence.facility_validator import FacilityValidator


def render_tab_facility_truth(validator: FacilityValidator):
    st.subheader("Facility Location Truth Inspector")
    st.write(
        "Deep-dive inspection of empirical centroids, government pin displacement, "
        "and side-by-side Track 1 vs. Track 2 score comparisons."
    )

    audit_df = validator.run_national_facility_audit()
    if audit_df.empty:
        st.warning("No facilities available for inspection.")
        return

    facility_list = list(audit_df["school_id_giga"].unique())
    selected_school_id = st.selectbox(
        "Select Target School Facility:", options=facility_list, index=0
    )

    if selected_school_id:
        eval_metrics = validator.evaluate_facility_location_confidence(
            selected_school_id
        )

        loc_flag = eval_metrics["location_verification_flag"]
        tags = eval_metrics["hardware_anomaly_tags"]
        tags_str = ", ".join(tags) if tags else "NONE"

        # Status Banners
        b_col1, b_col2 = st.columns(2)
        with b_col1:
            if loc_flag == "VERIFIED_ACCURATE":
                st.success(
                    f"🟢 **Track 1: VERIFIED ACCURATE**\n\nDisplacement: {eval_metrics['govt_displacement_m']}m | Score: {eval_metrics['location_confidence_score']}/100"
                )
            elif loc_flag == "GOVT_PIN_MISMATCH":
                st.error(
                    f"🔴 **Track 1: GOVERNMENT PIN MISMATCH**\n\nDisplacement: {eval_metrics['govt_displacement_m']}m | Score: {eval_metrics['location_confidence_score']}/100"
                )
            else:
                st.info(
                    f"🔵 **Track 1: {loc_flag}**\n\nScore: {eval_metrics['location_confidence_score']}/100"
                )

        with b_col2:
            if "BSSID_SPATIAL_SPLIT" in tags:
                st.warning(
                    f"🟠 **Track 2: HARDWARE ANOMALIES DETECTED**\n\nTags: [{tags_str}] | Health: {eval_metrics['hardware_health_score']}/100 (x{eval_metrics['p_coherence']})"
                )
            else:
                st.success(
                    f"🔵 **Track 2: HARDWARE HEALTHY**\n\nHealth Score: {eval_metrics['hardware_health_score']}/100 | Anomalies: NONE"
                )

        st.markdown("---")

        # Container 1: High-Resolution Spatial Map
        st.markdown("#### Spatial Verification Map (Decoupled View)")
        fig_map = validator.plot_facility_map(selected_school_id)
        st.plotly_chart(fig_map, use_container_width=True)

        st.markdown("---")

        # Container 2: Track 1 vs Track 2 Comparison Chart
        st.markdown("#### Two-Track Score Comparison Engine")
        fig_track = validator.plot_track_comparison(selected_school_id)
        st.plotly_chart(fig_track, use_container_width=True)

        st.markdown("---")

        # Container 3 & Phase 1 BSSID Profile: Side-by-Side
        c_col1, c_col2 = st.columns(2)
        with c_col1:
            st.markdown("#### 5-Factor Component Score Breakdown")
            fig_breakdown = validator.plot_score_breakdown(selected_school_id)
            st.plotly_chart(fig_breakdown, use_container_width=True)

        with c_col2:
            st.markdown("#### BSSID Temporal Profile (Operational Hours)")
            fig_bssid_temp = validator.spatial_profiler.plot_bssid_temporal_profile(
                selected_school_id
            )
            st.plotly_chart(fig_bssid_temp, use_container_width=True)
