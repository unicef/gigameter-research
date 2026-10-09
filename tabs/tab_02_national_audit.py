"""
Tab 2: national audit.

Country-level counts for every track and the recommended actions, the
location triage chart, and the facility table. Selecting a row opens the
facility in the inspector tab. Actions are shown as research statistics;
the dashboard does not export corrections.
"""

import streamlit as st

from src.spatial_intelligence.facility_validator import FacilityValidator
from src.spatial_intelligence.palette import ACTION_ORDER, FLAG_ORDER
from tabs.common import (
    ACTION_LABELS,
    DOCS,
    FLAG_LABELS,
    distance_column,
    open_facility,
    score_column,
    selected_row,
)

TABLE_KEY = "audit_table"
TABLE_IDS_KEY = "_audit_table_ids"

TABLE_COLUMNS = {
    "school_name": st.column_config.TextColumn("Facility", pinned=True),
    "school_id_giga": st.column_config.TextColumn("Facility ID"),
    "location_verification_flag": st.column_config.TextColumn("Flag"),
    "location_confidence_level": st.column_config.TextColumn("Confidence"),
    "location_confidence_score": score_column("Score"),
    "recommended_action": st.column_config.TextColumn("Action"),
    "govt_displacement_m": distance_column("Distance to pin"),
    "anchor_resolved_by": st.column_config.TextColumn("Anchor resolved by"),
    "hardware_health_score": score_column("Hardware score"),
    "hardware_anomaly_tags": st.column_config.TextColumn("Hardware tags"),
    "split_distance_m": distance_column("Cluster split"),
    "entity_attribution_flag": st.column_config.TextColumn("Attribution"),
    "nearest_other_entity_distance_m": distance_column("Nearest other pin"),
    "distinct_devices": st.column_config.NumberColumn("Devices"),
    "facility_device_days": st.column_config.NumberColumn("Device-days"),
}


def _open_selected_facility() -> None:
    row = selected_row(TABLE_KEY)
    ids = st.session_state.get(TABLE_IDS_KEY, [])
    if row is not None and row < len(ids):
        open_facility(ids[row])


def _metric_row(items) -> None:
    with st.container(horizontal=True):
        for label, value, help_text in items:
            st.metric(label, value, help=help_text, border=True)


def render_tab_national_audit(validator: FacilityValidator) -> None:
    summary = validator.summarize_national_audit()
    audit_df = validator.run_national_facility_audit()
    total = summary["total_facilities"]
    if total == 0:
        st.info("No facilities could be audited in this ledger.")
        return

    def share(count: int) -> str:
        return f"{count / total:.0%} of {total}"

    st.markdown(f"**Recommended actions** · research statistics, [Track 1 rules]({DOCS['track1']})")
    _metric_row(
        [
            ("Submit correction", summary["submit_correction"], "MISMATCH, HIGH confidence, two or more devices."),
            ("Field verify", summary["field_verify"], "Mismatch or ambiguous cases below the submit bar."),
            ("Await data", summary["await_data"], "Insufficient, unstable, or LOW confidence."),
            ("No action", summary["no_action"], "Verified facilities."),
        ]
    )

    st.markdown("**Track 1: location truth**")
    _metric_row(
        [
            (FLAG_LABELS[flag], summary[key], share(summary[key]))
            for flag, key in (
                ("VERIFIED_ACCURATE", "verified_accurate"),
                ("CAMPUS_DISPERSION", "campus_dispersion"),
                ("GOVT_PIN_MISMATCH", "govt_pin_mismatch"),
                ("AMBIGUOUS_MULTI_CLUSTER", "ambiguous_multi_cluster"),
                ("UNSTABLE_MOBILE_ONLY", "unstable_mobile_only"),
                ("NO_GOVT_PIN_AVAILABLE", "no_govt_pin_available"),
                ("INSUFFICIENT_DATA", "insufficient_data"),
            )
        ]
    )
    _metric_row(
        [
            ("HIGH confidence", summary["confidence_high"], share(summary["confidence_high"])),
            ("MEDIUM confidence", summary["confidence_medium"], share(summary["confidence_medium"])),
            ("LOW confidence", summary["confidence_low"], share(summary["confidence_low"])),
            (
                "Strategy agreement",
                f"{summary['strategy_agreement_pct']}%",
                f"Facilities where every anchor strategy picked the same cluster. [Strategies]({DOCS['strategies']})",
            ),
            (
                "Resolved by name match",
                summary["resolved_by_name_match"],
                "Strategies disagreed and exactly one candidate's SSID matched the registry name.",
            ),
        ]
    )

    st.markdown(f"**Track 2: hardware integrity** · [rules]({DOCS['track2']})")
    _metric_row(
        [
            (
                "Stationary-anchored",
                f"{summary['stationary_pct']}%",
                f"{summary['stationary_facilities']} facilities with a STATIONARY device in the scoring cluster.",
            ),
            ("Coherence penalty", summary["coherence_penalised"], "Facilities whose supported clusters are far enough apart to reduce the hardware score."),
            ("BSSID spatial split", summary["bssid_spatial_splits"], share(summary["bssid_spatial_splits"])),
            ("Hotspot-tethered", summary["hotspot_tethered_facilities"], share(summary["hotspot_tethered_facilities"])),
            ("Commuter device in anchor", summary["commuter_device_facilities"], share(summary["commuter_device_facilities"])),
            ("Relocated device", summary["relocated_device_facilities"], share(summary["relocated_device_facilities"])),
        ]
    )

    st.markdown(f"**Track 3: entity attribution** · [rules]({DOCS['track3']})")
    _metric_row(
        [
            ("Consistent", summary["attribution_consistent"], share(summary["attribution_consistent"])),
            (
                "Other entity nearby",
                summary["other_entity_nearby"],
                f"Another facility's pin within {validator.config.other_entity_radius_m:g} m of the anchor.",
            ),
            ("Unresolved", summary["attribution_unresolved"], share(summary["attribution_unresolved"])),
        ]
    )

    left, right = st.columns([3, 2])
    with left.container(border=True):
        st.markdown("**Location triage**")
        st.caption("Anchor distance to the official pin against confidence. Facilities without a distance are not plotted.")
        st.plotly_chart(validator.plot_location_triage(), width="stretch")
    with right.container(border=True):
        st.markdown("**Flags by confidence tier**")
        st.plotly_chart(validator.plot_flag_confidence_breakdown(), width="stretch")

    left, right = st.columns(2)
    with left.container(border=True):
        st.markdown(f"**Device mobility classes** · [rules]({DOCS['mobility']})")
        st.plotly_chart(validator.mobility_analyzer.plot_national_mobility_distribution(), width="stretch")
    with right.container(border=True):
        st.markdown("**Stationary hardware coverage**")
        st.plotly_chart(validator.plot_stationary_facility_percentage(), width="stretch")

    with st.container(border=True):
        st.markdown("**Facilities**")
        with st.container(horizontal=True):
            flags = st.pills(
                "Flag",
                FLAG_ORDER,
                selection_mode="multi",
                format_func=lambda f: FLAG_LABELS.get(f, f),
                key="audit_flag_filter",
            )
            actions = st.pills(
                "Action",
                ACTION_ORDER,
                selection_mode="multi",
                format_func=lambda a: ACTION_LABELS.get(a, a),
                key="audit_action_filter",
            )
        table = audit_df
        if flags:
            table = table[table["location_verification_flag"].isin(flags)]
        if actions:
            table = table[table["recommended_action"].isin(actions)]
        table = table.sort_values(["location_confidence_score"], ascending=False).reset_index(drop=True)
        st.session_state[TABLE_IDS_KEY] = table["school_id_giga"].tolist()
        st.caption(f"{len(table)} of {total} facilities. Select a row to open it in the facility inspector.")
        st.dataframe(
            table[[c for c in TABLE_COLUMNS if c in table.columns]],
            column_config=TABLE_COLUMNS,
            hide_index=True,
            width="stretch",
            height=480,
            key=TABLE_KEY,
            on_select=_open_selected_facility,
            selection_mode="single-row",
        )
