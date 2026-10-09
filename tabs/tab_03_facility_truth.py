"""
Tab 3: facility inspector.

Everything the methodology decided for one facility: the three tracks, the
strategy candidates and how the anchor was resolved, the map, the evidence
over time, the observation clusters, the devices, and the BSSIDs.
"""

import pandas as pd
import streamlit as st

from src.spatial_intelligence.facility_validator import FacilityValidator
from tabs.common import (
    ACTION_BADGE,
    ACTION_LABELS,
    ATTRIBUTION_BADGE,
    CONFIDENCE_BADGE,
    DOCS,
    FACILITY_KEY,
    FLAG_BADGE,
    FLAG_LABELS,
    MOBILITY_BADGE,
    TAG_LABELS,
    badge,
    distance_column,
    facility_label,
    fmt_m,
    open_device,
    pct_column,
    selected_row,
)

DEVICE_TABLE_KEY = "facility_devices_table"
DEVICE_IDS_KEY = "_facility_device_ids"

FLAG_NOTES = {
    "VERIFIED_ACCURATE": ("success", "The anchor is within {verified:g} m of the official pin."),
    "CAMPUS_DISPERSION": ("info", "The anchor is {distance} from the pin: between the verified and mismatch bands."),
    "GOVT_PIN_MISMATCH": ("warning", "The anchor is {distance} from the official pin, beyond {mismatch:g} m."),
    "AMBIGUOUS_MULTI_CLUSTER": (
        "warning",
        "The strategies chose different clusters and no name match broke the tie. "
        "The score uses the telemetry-dominance candidate.",
    ),
    "UNSTABLE_MOBILE_ONLY": ("warning", "No cluster has enough device-days, so the anchor is not supported."),
    "NO_GOVT_PIN_AVAILABLE": ("info", "The facility has no official pin to compare against."),
    "INSUFFICIENT_DATA": ("info", "Fewer than {min_days} device-days of weekday operational-hours evidence."),
}
TAG_NOTES = {
    "BSSID_SPATIAL_SPLIT": "Supported clusters are {split} apart.",
    "HOTSPOT_TETHERED_FACILITY": "{hotspot:.0f}% of fix events come from hotspot networks.",
    "COMMUTER_DEVICE": "A COMMUTER device contributes to the anchor cluster.",
    "RELOCATED_DEVICE": "A RELOCATED device reported for this facility.",
}

CLUSTER_COLUMNS = {
    "facility_cluster_id": st.column_config.NumberColumn("Cluster"),
    "is_anchor_cluster": st.column_config.CheckboxColumn("Anchor"),
    "is_candidate": st.column_config.CheckboxColumn("Candidate"),
    "is_supported": st.column_config.CheckboxColumn("Supported"),
    "dist_to_govt_m": distance_column("Distance to pin"),
    "device_days": st.column_config.NumberColumn("Device-days"),
    "devices": st.column_config.NumberColumn("Devices"),
    "events": st.column_config.NumberColumn("Fix events"),
    "first_date": st.column_config.TextColumn("First date"),
    "last_date": st.column_config.TextColumn("Last date"),
    "ssids": st.column_config.ListColumn("SSIDs"),
    "bssids": st.column_config.ListColumn("BSSIDs"),
    "ssid_name_match": st.column_config.CheckboxColumn("Name match"),
    "hotspot_share": st.column_config.NumberColumn("Hotspot share", format="percent"),
    "mean_accuracy_m": distance_column("Mean accuracy"),
}
DEVICE_COLUMNS = {
    "device_id": st.column_config.TextColumn("Device"),
    "mobility_class": st.column_config.TextColumn("Class"),
    "evidence_device_days": st.column_config.NumberColumn("Evidence days"),
    "total_fix_events": st.column_config.NumberColumn("Fix events"),
    "supported_cluster_count": st.column_config.NumberColumn("Supported clusters"),
    "cluster_transitions": st.column_config.NumberColumn("Transitions"),
    "compliance_rate_pct": pct_column("Inside geofence"),
}
BSSID_COLUMNS = {
    "detected_wifi_bssid": st.column_config.TextColumn("BSSID"),
    "last_known_ssid": st.column_config.TextColumn("Last SSID"),
    "fix_events": st.column_config.NumberColumn("Fix events"),
    "carried_observations": st.column_config.NumberColumn("Carried rows"),
    "total_observations": st.column_config.NumberColumn("Rows"),
    "days_active": st.column_config.NumberColumn("Days"),
    "distinct_devices": st.column_config.NumberColumn("Devices"),
    "pct_operational_hours": pct_column("Operational hours"),
    "avg_accuracy_radius_m": distance_column("Mean accuracy"),
    "is_mobile_hotspot": st.column_config.CheckboxColumn("Hotspot"),
    "is_mobile_bssid": st.column_config.CheckboxColumn("Moving router"),
    "is_laa_bssid": st.column_config.CheckboxColumn("Randomised MAC"),
}


def _open_selected_device(school_id: str) -> None:
    row = selected_row(DEVICE_TABLE_KEY)
    ids = st.session_state.get(DEVICE_IDS_KEY, [])
    if row is not None and row < len(ids):
        open_device(school_id, ids[row])


def _notes(res: dict, validator: FacilityValidator) -> None:
    cfg = validator.config
    kind, text = FLAG_NOTES[res["location_verification_flag"]]
    message = text.format(
        verified=cfg.verified_max_m,
        mismatch=cfg.mismatch_min_m,
        distance=fmt_m(res["govt_displacement_m"]),
        min_days=cfg.min_support_device_days,
    )
    getattr(st, kind)(message, icon=":material/location_on:")
    for tag in res["hardware_anomaly_tags"]:
        st.warning(
            f"**{TAG_LABELS.get(tag, tag)}.** "
            + TAG_NOTES.get(tag, "").format(split=fmt_m(res["split_distance_m"]), hotspot=res["hotspot_event_pct"] or 0),
            icon=":material/router:",
        )
    if res["entity_attribution_flag"] == "OTHER_ENTITY_NEARBY":
        st.warning(
            f"**Other entity nearby.** Facility `{res['nearest_other_entity_id']}` has its pin "
            f"{fmt_m(res['nearest_other_entity_distance_m'])} from the anchor; the telemetry may belong to it.",
            icon=":material/domain:",
        )


def _track_cards(res: dict) -> None:
    one, two, three = st.columns(3)
    with one.container(border=True, height="stretch"):
        st.markdown(f"**Track 1: location truth** · [rules]({DOCS['track1']})")
        st.markdown(
            badge(res["location_verification_flag"], FLAG_BADGE, FLAG_LABELS)
            + " "
            + badge(res["location_confidence_level"], CONFIDENCE_BADGE)
            + " "
            + badge(res["recommended_action"], ACTION_BADGE, ACTION_LABELS)
        )
        with st.container(horizontal=True):
            st.metric("Confidence", f"{res['location_confidence_score']:.1f}")
            st.metric("Distance to pin", fmt_m(res["govt_displacement_m"]))
    with two.container(border=True, height="stretch"):
        st.markdown(f"**Track 2: hardware integrity** · [rules]({DOCS['track2']})")
        tags = res["hardware_anomaly_tags"]
        st.markdown(" ".join(f":orange-badge[{TAG_LABELS.get(t, t)}]" for t in tags) or ":green-badge[No tags]")
        with st.container(horizontal=True):
            st.metric("Hardware score", f"{res['hardware_health_score']:.1f}")
            st.metric("Coherence", f"×{res['p_coherence']:.2f}", help="Penalty from the distance between supported clusters.")
            st.metric("Cluster split", fmt_m(res["split_distance_m"]))
    with three.container(border=True, height="stretch"):
        st.markdown(f"**Track 3: entity attribution** · [rules]({DOCS['track3']})")
        st.markdown(
            badge(res["entity_attribution_flag"], ATTRIBUTION_BADGE)
            + " "
            + (":green-badge[SSID matches name]" if res["ssid_name_match"] else ":gray-badge[No SSID name match]")
        )
        with st.container(horizontal=True):
            st.metric("Nearest other pin", fmt_m(res["nearest_other_entity_distance_m"]))
            st.metric("Pins", res["entity_pins_source"].replace("_", " "))


def _strategy_panel(res: dict, clusters: pd.DataFrame) -> None:
    st.markdown(f"**Anchor selection** · [strategies]({DOCS['strategies']})")
    by_id = clusters.set_index("facility_cluster_id") if not clusters.empty else pd.DataFrame()
    rows = []
    for strategy, cluster_id in (res["strategy_candidates"] or {}).items():
        cluster = by_id.loc[cluster_id] if cluster_id in by_id.index else None
        rows.append(
            {
                "strategy": strategy,
                "cluster": cluster_id,
                "distance_to_pin": (res["candidate_govt_displacement_m"] or {}).get(strategy),
                "device_days": None if cluster is None else cluster["device_days"],
                "name_match": None if cluster is None else bool(cluster["ssid_name_match"]),
                "anchor": cluster_id == res["anchor_cluster_id"],
            }
        )
    if rows:
        st.dataframe(
            pd.DataFrame(rows),
            hide_index=True,
            width="stretch",
            column_config={
                "strategy": "Strategy",
                "cluster": st.column_config.NumberColumn("Cluster"),
                "distance_to_pin": distance_column("Distance to pin"),
                "device_days": st.column_config.NumberColumn("Device-days"),
                "name_match": st.column_config.CheckboxColumn("Name match"),
                "anchor": st.column_config.CheckboxColumn("Anchor"),
            },
        )
    st.markdown(
        f"Resolved by: `{res['anchor_resolved_by']}`  \n"
        f"Agreement: {'yes' if res['strategy_agreement'] else 'no'} · "
        f"anchor support {res['anchor_support_device_days']} device-days from {res['anchor_support_devices']} devices"
    )
    if res["strategy_fallback_reason"]:
        st.caption(f"Fallbacks: {res['strategy_fallback_reason']}")


def render_tab_facility_truth(validator: FacilityValidator, geofence_radius_m: float) -> None:
    audit_df = validator.run_national_facility_audit()
    if audit_df.empty:
        st.info("No facilities could be audited in this ledger.")
        return

    names = dict(zip(audit_df["school_id_giga"], audit_df["school_name"]))
    options = sorted(names, key=lambda s: str(names.get(s) or s).lower())
    if st.session_state.get(FACILITY_KEY) not in options:
        st.session_state[FACILITY_KEY] = options[0]
    school_id = st.selectbox(
        "Facility",
        options=options,
        format_func=lambda s: facility_label(s, names),
        key=FACILITY_KEY,
        help="Type to search by name or ID. Rows selected in the national audit open here.",
    )

    res = validator.evaluate_facility_location_confidence(school_id)
    if "error" in res:
        st.error(res["error"])
        return

    st.subheader(res["school_name"], anchor=False)
    st.caption(
        f"`{school_id}` · {res['distinct_devices']} devices · {res['total_fix_events']:,} fix events · "
        f"{res['facility_device_days']} device-days in the anchor window · config `{res['config_hash']}`"
    )
    _notes(res, validator)
    _track_cards(res)

    clusters = validator.facility_cluster_table(school_id)
    left, right = st.columns([3, 2])
    with left.container(border=True):
        st.markdown(f"**Map** · fix events by [observation cluster]({DOCS['clusters']})")
        st.plotly_chart(validator.plot_facility_map(school_id, geofence_radius_m=geofence_radius_m), width="stretch")
    with right:
        with st.container(border=True):
            _strategy_panel(res, clusters)
        with st.container(border=True):
            score_label = (
                f"cluster {res['score_cluster_id']}" if res["score_cluster_id"] is not None else "no cluster"
            )
            st.markdown(f"**Raw score breakdown** · {score_label} · [S_raw]({DOCS['raw_score']})")
            st.plotly_chart(validator.plot_score_breakdown(school_id), width="stretch")

    with st.container(border=True):
        st.markdown("**Evidence over time** · fix events per day and cluster")
        st.plotly_chart(validator.plot_facility_evidence_timeline(school_id), width="stretch")

    with st.container(border=True):
        st.markdown("**Observation clusters** · weekday operational-hours fix events")
        if clusters.empty:
            st.caption("No anchor-window fix events.")
        else:
            st.dataframe(
                clusters[[c for c in CLUSTER_COLUMNS if c in clusters.columns]],
                column_config=CLUSTER_COLUMNS,
                hide_index=True,
                width="stretch",
            )

    left, right = st.columns(2)
    with left.container(border=True):
        st.markdown("**Devices** · select a row to open it in device mobility")
        report = validator.mobility_analyzer.generate_facility_mobility_report()
        devices = (
            report[report["school_id_giga"] == school_id].reset_index(drop=True)
            if not report.empty
            else pd.DataFrame()
        )
        if devices.empty:
            st.caption("No devices.")
        else:
            st.markdown(
                " ".join(
                    f"{badge(cls, MOBILITY_BADGE)} {count}"
                    for cls, count in devices["mobility_class"].value_counts().items()
                )
            )
            st.session_state[DEVICE_IDS_KEY] = devices["device_id"].tolist()
            st.dataframe(
                devices[[c for c in DEVICE_COLUMNS if c in devices.columns]],
                column_config=DEVICE_COLUMNS,
                hide_index=True,
                width="stretch",
                key=DEVICE_TABLE_KEY,
                on_select=lambda: _open_selected_device(school_id),
                selection_mode="single-row",
            )
    with right.container(border=True):
        st.markdown(f"**BSSIDs** · [hotspot signals]({DOCS['hotspots']})")
        profiles = validator.spatial_profiler.build_bssid_profiles()
        profiles = profiles[profiles["school_id_giga"] == school_id] if not profiles.empty else profiles
        if profiles.empty:
            st.caption("No BSSIDs recorded.")
        else:
            st.dataframe(
                profiles[[c for c in BSSID_COLUMNS if c in profiles.columns]],
                column_config=BSSID_COLUMNS,
                hide_index=True,
                width="stretch",
            )
