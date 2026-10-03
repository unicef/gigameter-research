"""
Tab 2: Two-Track Executive National Audit & Government Validation Dataframe.
"""

import streamlit as st
from src.spatial_intelligence.facility_validator import FacilityValidator
from src.spatial_intelligence.mobility_analyzer import MobilityAnalyzer


def render_tab_national_audit(
    country_iso3: str, validator: FacilityValidator, mobility_engine: MobilityAnalyzer
):
    st.subheader(f"National Executive Audit - {country_iso3}")
    st.write(
        "Cross-referencing crowdsourced empirical field telemetry against official "
        "government administrative records using the Two-Track Validation Engine."
    )

    with st.spinner("Executing Two-Track Engine and caching national audit results..."):
        audit_df = validator.run_national_facility_audit()
        audit_summary = validator.summarize_national_audit()

    if audit_df.empty:
        st.warning("No valid facilities found for national audit execution.")
        return

    # -------------------------------------------------------------------
    # 1. Two-Track Metric Cards
    # -------------------------------------------------------------------
    st.markdown("##### Track 1: Location Truth KPIs")
    t1_c1, t1_c2, t1_c3, t1_c4 = st.columns(4)
    t1_c1.metric("Total Facilities Evaluated", audit_summary["total_facilities"])
    t1_c2.metric(
        "Verified Accurate (<= 200m)",
        audit_summary["verified_accurate"],
    )
    t1_c3.metric(
        "Govt Pin Mismatches (> 500m)",
        audit_summary["govt_pin_mismatch"],
        delta_color="inverse",
    )
    t1_c4.metric(
        "Campus Dispersion (200m - 500m)",
        audit_summary["campus_dispersion"],
    )

    st.markdown("##### Track 2: Hardware Health KPIs")
    t2_c1, t2_c2, t2_c3, t2_c4 = st.columns(4)

    t2_c1.metric(
        "Facilities with Fixed Hardware",
        (
            f"{audit_summary['stationary_pct']}% "
            f"({audit_summary['stationary_facilities']}/{audit_summary['total_facilities']})"
        ),
    )
    t2_c2.metric(
        "BSSID Spatial Splits (> 2km)",
        audit_summary["bssid_spatial_splits"],
        delta_color="inverse",
    )
    t2_c3.metric(
        "Mobile Hotspot Tethered Facilities",
        audit_summary["hotspot_tethered_facilities"],
        delta_color="inverse",
    )
    t2_c4.metric(
        "Mean Hardware Health Score",
        f"{audit_summary['mean_hardware_health_score']} / 100",
    )

    st.markdown("---")

    # -------------------------------------------------------------------
    # 2. Phase 1 Visualizations: Actionability Matrix & Mobility Distribution
    # -------------------------------------------------------------------
    v_col1, v_col2 = st.columns(2)

    with v_col1:
        st.markdown("##### Two-Track Triage & Actionability Matrix")
        try:
            fig_matrix = validator.plot_two_track_actionability_matrix()
            st.plotly_chart(fig_matrix, use_container_width=True)
        except Exception as e:
            st.warning(f"Could not render actionability matrix: {e}")

    with v_col2:
        st.markdown("##### National Device Mobility Breakdown")
        try:
            fig_mob_dist = mobility_engine.plot_national_mobility_distribution()
            st.plotly_chart(fig_mob_dist, use_container_width=True)
        except Exception as e:
            st.warning(f"Could not render mobility distribution: {e}")

    st.markdown("---")

    # -------------------------------------------------------------------
    # 3. Audit Table Display
    # -------------------------------------------------------------------
    loc_flag_filter = st.multiselect(
        "Filter Table by Location Verification Flag (Track 1):",
        options=list(audit_df["location_verification_flag"].unique()),
        default=list(audit_df["location_verification_flag"].unique()),
    )

    filtered_audit = audit_df[
        audit_df["location_verification_flag"].isin(loc_flag_filter)
    ]

    st.dataframe(
        filtered_audit[
            [
                "school_id_giga",
                "school_name",
                "location_confidence_score",
                "location_verification_flag",
                "govt_displacement_m",
                "hardware_health_score",
                "hardware_anomaly_tags",
                "empirical_latitude",
                "empirical_longitude",
                "stationary_devices_count",
                "govt_latitude",
                "govt_longitude",
                "commuter_devices_count",
                "relocated_devices_count",
                "high_mobility_devices_count",
                "total_scans",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

    csv_bytes = filtered_audit.to_csv(index=False).encode("utf-8")
    st.download_button(
        label=f"📥 Export {country_iso3} Two-Track Government GIS Corrections (CSV)",
        data=csv_bytes,
        file_name=f"{country_iso3}_two_track_government_gis_corrections.csv",
        mime="text/csv",
    )
