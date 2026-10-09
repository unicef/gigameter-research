"""
Tab 4: device mobility.

The evidence behind one device's mobility class: its clusters, how often it
moves between them, how they spread over dates and hours, and how much of
its time falls inside the geofence around the reference point.
"""

import streamlit as st

from src.spatial_intelligence.facility_validator import FacilityValidator
from src.spatial_intelligence.mobility_analyzer import REFERENCE_FACILITY_ANCHOR
from tabs.common import DEVICE_KEY, DEVICE_SCHOOL_KEY, DOCS, MOBILITY_BADGE, badge, facility_label, fmt_m


def render_tab_device_mobility(validator: FacilityValidator) -> None:
    analyzer = validator.mobility_analyzer
    report = analyzer.generate_facility_mobility_report()
    if report.empty:
        st.info("No devices with fix events in this ledger.")
        return

    names = dict(zip(report["school_id_giga"], report["school_name"]))
    schools = sorted(names, key=lambda s: str(names.get(s) or s).lower())
    if st.session_state.get(DEVICE_SCHOOL_KEY) not in schools:
        st.session_state[DEVICE_SCHOOL_KEY] = schools[0]

    pick_school, pick_device = st.columns(2)
    school_id = pick_school.selectbox(
        "Facility",
        options=schools,
        format_func=lambda s: facility_label(s, names),
        key=DEVICE_SCHOOL_KEY,
    )
    devices = report[report["school_id_giga"] == school_id].sort_values(
        "evidence_device_days", ascending=False
    )
    by_device = devices.set_index("device_id")
    options = devices["device_id"].tolist()
    if st.session_state.get(DEVICE_KEY) not in options:
        st.session_state[DEVICE_KEY] = options[0]
    device_id = pick_device.selectbox(
        "Device",
        options=options,
        format_func=lambda d: (
            f"{d} · {by_device.loc[d, 'mobility_class']} · {by_device.loc[d, 'evidence_device_days']} days"
        ),
        key=DEVICE_KEY,
    )

    res = analyzer.analyze_device_mobility(device_id)
    if "error" in res:
        st.error(res["error"])
        return

    reference = (
        "the facility anchor"
        if res["reference_source"] == REFERENCE_FACILITY_ANCHOR
        else "the device's dominant cluster (no facility anchor)"
    )
    st.markdown(
        f"{badge(res['mobility_class'], MOBILITY_BADGE)} · [classification rules]({DOCS['mobility']}) · "
        f"config `{res['config_hash']}`"
    )
    with st.container(horizontal=True):
        st.metric("Evidence days", res["evidence_device_days"], border=True, help="Distinct local dates with fix events.")
        st.metric(
            "Fix events",
            f"{res['total_fix_events']:,}",
            help=f"{res['total_scans']:,} rows, of which {res['carried_scans']:,} carried.",
            border=True,
        )
        st.metric(
            "Supported clusters",
            f"{res['supported_cluster_count']} of {res['cluster_count']}",
            help=f"Clusters spanning at least {analyzer.config.min_cluster_device_days} days.",
            border=True,
        )
        st.metric("Noise share", f"{res['noise_share']:.0%}", border=True, help="Fix events outside any cluster.")
        st.metric(
            "Transitions",
            res["cluster_transitions"],
            help="Changes of supported cluster between consecutive fix events, ignoring noise.",
            border=True,
        )
        st.metric(
            "Inside geofence",
            f"{res['compliance_rate_pct']}%",
            help=(
                f"Fix events within {analyzer.geofence_radius_m:g} m of {reference}. "
                f"Median distance {fmt_m(res['median_displacement_m'])}, max {fmt_m(res['max_displacement_m'])}."
            ),
            border=True,
        )

    left, right = st.columns([3, 2])
    with left.container(border=True):
        st.markdown("**Map** · fix events by device cluster")
        st.plotly_chart(analyzer.plot_device_mobility_map(device_id), width="stretch")
    with right:
        with st.container(border=True):
            st.markdown("**Clusters over time** · fix events per day")
            st.plotly_chart(analyzer.plot_cluster_calendar(device_id), width="stretch")
        with st.container(border=True):
            st.markdown("**Distance by hour of day**")
            st.plotly_chart(analyzer.plot_commuter_time_of_day_scatter(device_id), width="stretch")

    with st.container(border=True):
        st.markdown(f"**Distance from {reference} over time**")
        st.plotly_chart(analyzer.plot_displacement_timeline(device_id), width="stretch")
