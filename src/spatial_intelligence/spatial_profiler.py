"""
Module: src/spatial_intelligence/spatial_profiler.py
Purpose: Pillar 2 spatial profiling. Tags mobile hotspots, clusters each
         facility's fix events into observation clusters, and selects the
         facility anchor with the configured strategies.
Rules: Settings come from SpatialConfig. Evidence is counted in fix events
       and device-days. A centroid is only ever computed inside one cluster;
       no facility coordinate is an average across clusters.
"""

from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from gigaspatial.processing import calculate_distance as haversine_distance_meters

from src.utils.data_loader import TelemetryLoader

from .config import (
    DEFAULT_CONFIG,
    STRATEGY_GOVT_PROXIMITY,
    STRATEGY_STATIONARY_FIRST,
    STRATEGY_TELEMETRY_DOMINANCE,
    SpatialConfig,
)
from .fix_events import build_fix_event_table, mark_fix_events
from .geo import dbscan_labels, haversine_m, max_pairwise_distance_m, weighted_centroid
from .name_match import ssid_matches_name

RESOLVED_BY_AGREEMENT = "strategy_agreement"
RESOLVED_BY_SINGLE_STRATEGY = "single_strategy"
RESOLVED_BY_NAME_MATCH = "ssid_name_match"
RESOLVED_BY_UNRESOLVED = "unresolved"
RESOLVED_BY_NO_CLUSTER = "no_cluster"

FALLBACK_NO_GOVT_PIN = "no_govt_pin"
FALLBACK_NO_CLUSTER_IN_RADIUS = "no_cluster_within_govt_anchor_radius"
FALLBACK_NO_DEVICE_CLASSES = "no_device_classes"
FALLBACK_NO_STATIONARY_EVIDENCE = "no_stationary_evidence"


class ClusterResolutionStrategy(Enum):
    """Anchor strategies. Values match the strategy names in `SpatialConfig`."""

    TELEMETRY_DOMINANCE = STRATEGY_TELEMETRY_DOMINANCE
    GOVT_PROXIMITY_ANCHOR = STRATEGY_GOVT_PROXIMITY
    STATIONARY_FIRST = STRATEGY_STATIONARY_FIRST


def _extract_coord_tuples(df_subset: pd.DataFrame) -> List[Tuple[float, float]]:
    """Extracts valid (latitude, longitude) coordinate tuples from a DataFrame subset."""
    valid_mask = (
        df_subset["detected_latitude"].notna() & df_subset["detected_longitude"].notna()
    )
    valid_coords = df_subset.loc[valid_mask, ["detected_latitude", "detected_longitude"]]
    return [tuple(x) for x in valid_coords.to_numpy()]


def is_locally_administered(bssid: Any) -> bool:
    """True when the MAC address has the locally administered bit set."""
    if not isinstance(bssid, str) or len(bssid) < 2:
        return False
    try:
        return bool(int(bssid[:2], 16) & 0x02)
    except ValueError:
        return False


def _first_valid(series: pd.Series) -> Any:
    valid = series.dropna()
    return valid.iloc[0] if not valid.empty else np.nan


def _unique_values(series: pd.Series) -> List[Any]:
    return sorted({v for v in series.dropna()})


class SpatialProfiler:
    """
    Spatial analytics engine for GigaMeter telemetry.

    On load, every row is tagged with:

    * `is_hotspot_ssid`: the SSID matches `config.hotspot_ssid_pattern`.
    * `is_laa_bssid`: the BSSID is a locally administered MAC (evidence only).
    * `is_mobile_bssid`: the BSSID's accuracy-gated, non-carried fix events
      form two or more clusters that each span
      `bssid_mobility_min_cluster_days`.
    * `is_mobile_hotspot`: `is_hotspot_ssid` or `is_mobile_bssid`.

    `build_facility_spatial_summary` then clusters each facility's
    anchor-window fix events and selects one anchor cluster.
    """

    def __init__(
        self,
        telemetry_df: Optional[pd.DataFrame] = None,
        *,
        file_path: Optional[Union[str, Path]] = None,
        query_name: Optional[str] = None,
        query_params: Optional[Mapping[str, Any]] = None,
        country_iso3: Optional[str] = None,
        schools_df: Optional[pd.DataFrame] = None,
        timestamp_col: str = "created_timestamp",
        db: Any = None,
        delta_store: Any = None,
        config: SpatialConfig = DEFAULT_CONFIG,
    ) -> None:
        """
        Load a canonical telemetry frame, tag hotspots, and build fix events.

        Provide exactly one of `telemetry_df`, `file_path`, or `query_name`.
        School-pin merge and local-time enrichment are performed by
        `TelemetryLoader` before tagging.

        Args:
            telemetry_df: In-memory measurements.
            file_path: `.csv` or `.parquet` ledger path.
            query_name: SQL template stem under `sql/`.
            query_params: Placeholder values for the SQL template.
            country_iso3: Country code used to load Delta school pins.
            schools_df: Official school metadata used when govt pins are absent.
            timestamp_col: UTC timestamp column used during local-time enrichment.
            db: Optional database client. Built from `.env` when a query needs one.
            delta_store: Optional Delta Sharing client. Built from `.env` when
                school pins must be loaded.
            config: Methodology settings.
        """
        self.config = config
        self.df = TelemetryLoader().load(
            telemetry_df=telemetry_df,
            file_path=file_path,
            query_name=query_name,
            query_params=query_params,
            country_iso3=country_iso3,
            schools_df=schools_df,
            timestamp_col=timestamp_col,
            db=db,
            delta_store=delta_store,
        )
        self._tag_mobile_hotspots()

        self.facility_clusters: Optional[pd.DataFrame] = None
        self.facility_events: Optional[pd.DataFrame] = None

    # ------------------------------------------------------------------
    # Hotspot and BSSID mobility
    # ------------------------------------------------------------------
    def _tag_mobile_hotspots(self) -> None:
        df = self.df
        if "detected_wifi_ssid" in df.columns:
            ssid = df["detected_wifi_ssid"].astype(object)
            df["is_hotspot_ssid"] = (
                ssid.where(ssid.notna(), "")
                .astype(str)
                .str.contains(self.config.hotspot_ssid_pattern, regex=True, na=False)
            )
        else:
            df["is_hotspot_ssid"] = False

        has_bssid = "detected_wifi_bssid" in df.columns
        df["is_laa_bssid"] = (
            df["detected_wifi_bssid"].map(is_locally_administered).astype(bool)
            if has_bssid
            else False
        )

        valid = df[df["detected_latitude"].notna() & df["detected_longitude"].notna()]
        rows = mark_fix_events(valid, self.config)
        self.mobile_bssids = self._find_mobile_bssids(rows) if has_bssid else set()

        df["is_mobile_bssid"] = (
            df["detected_wifi_bssid"].isin(self.mobile_bssids) if has_bssid else False
        )
        df["is_mobile_hotspot"] = df["is_hotspot_ssid"] | df["is_mobile_bssid"]

        tag_columns = ["is_hotspot_ssid", "is_laa_bssid", "is_mobile_bssid", "is_mobile_hotspot"]
        rows[tag_columns] = df.loc[rows.index, tag_columns]
        self.fix_event_rows = rows
        self.fix_events = build_fix_event_table(rows, self.config, marked=True)

    def _find_mobile_bssids(self, rows: pd.DataFrame) -> set:
        cfg = self.config
        events = build_fix_event_table(rows, cfg, marked=True)
        if events.empty:
            return set()
        events = events[events["detected_wifi_bssid"].notna()]
        if "detected_location_accuracy" in events.columns:
            accuracy = pd.to_numeric(events["detected_location_accuracy"], errors="coerce")
            events = events[accuracy <= cfg.bssid_mobility_accuracy_gate_m]
        mobile = set()
        for bssid, group in events.groupby("detected_wifi_bssid"):
            if len(group) < 2 * cfg.bssid_mobility_min_samples:
                continue
            labels = dbscan_labels(
                group["detected_latitude"],
                group["detected_longitude"],
                cfg.bssid_mobility_eps_m,
                cfg.bssid_mobility_min_samples,
            )
            days = group.assign(_label=labels)
            days = days[days["_label"] >= 0].groupby("_label")["local_date"].nunique()
            if (days >= cfg.bssid_mobility_min_cluster_days).sum() >= 2:
                mobile.add(bssid)
        return mobile

    # ------------------------------------------------------------------
    # Governance and BSSID tables
    # ------------------------------------------------------------------
    def summarize_governance(self) -> Dict[str, Any]:
        """
        Summarize ledger quality for the governance metric cards.

        Counts are taken from the full frame held by this profiler, including
        rows without coordinates. Percentages are rounded to one decimal.
        A zero row count yields 0.0, except `operational_hours_pct`, which is
        100.0 when the flag is absent or there are no rows.

        Returns:
            Total records, ambient-scan and hotspot shares, mean location
            accuracy in meters, and the operational-hours share.
        """
        total_records = len(self.df)

        def pct(count: float) -> float:
            return round(count / total_records * 100.0, 1) if total_records > 0 else 0.0

        ambient_scans = (
            int(self.df["detected_wifi_bssid"].isna().sum())
            if "detected_wifi_bssid" in self.df.columns and total_records > 0
            else 0
        )
        mean_accuracy_m = (
            round(float(self.df["detected_location_accuracy"].mean()), 1)
            if "detected_location_accuracy" in self.df.columns and total_records > 0
            else 0.0
        )
        operational_hours_pct = (
            pct(self.df["is_operational_hours"].sum())
            if "is_operational_hours" in self.df.columns and total_records > 0
            else 100.0
        )
        hotspot_scans = int(self.df["is_mobile_hotspot"].sum()) if total_records > 0 else 0

        return {
            "total_records": total_records,
            "ambient_scans": ambient_scans,
            "ambient_pct": pct(ambient_scans),
            "mean_accuracy_m": mean_accuracy_m,
            "operational_hours_pct": operational_hours_pct,
            "hotspot_scans": hotspot_scans,
            "hotspot_pct": pct(hotspot_scans),
        }

    def build_bssid_profiles(self) -> pd.DataFrame:
        """
        One row per school and non-null BSSID.

        Returns:
            Observation, fix-event, and carried counts, active days, devices,
            operational-hours split, mean accuracy, hotspot and mobility flags,
            and the BSSID's coordinate tuples.
        """
        bssid_col = "detected_wifi_bssid"
        if bssid_col not in self.df.columns:
            return pd.DataFrame()
        bssid_df = self.df[self.df[bssid_col].notna()]
        if bssid_df.empty:
            return pd.DataFrame()

        marked = self.fix_event_rows[self.fix_event_rows[bssid_col].notna()]
        event_counts = (
            marked[~marked["fix_carried"]]
            .groupby(["school_id_giga", bssid_col])["fix_event_id"]
            .nunique()
        )
        carried_counts = marked.groupby(["school_id_giga", bssid_col])["fix_carried"].sum()

        profiles = []
        for (school_id, bssid), group in bssid_df.groupby(["school_id_giga", bssid_col]):
            total_obs = len(group)
            op_obs = int(group["is_operational_hours"].sum())
            coord_tuples = _extract_coord_tuples(group)
            ssids = group["detected_wifi_ssid"].dropna() if "detected_wifi_ssid" in group else pd.Series(dtype=object)
            profiles.append(
                {
                    "school_id_giga": school_id,
                    "detected_wifi_bssid": bssid,
                    "last_known_ssid": ssids.iloc[-1] if not ssids.empty else None,
                    "is_mobile_hotspot": bool(group["is_mobile_hotspot"].any()),
                    "is_mobile_bssid": bool(group["is_mobile_bssid"].any()),
                    "is_laa_bssid": bool(group["is_laa_bssid"].any()),
                    "distinct_devices": int(group["device_id"].nunique()),
                    "total_observations": total_obs,
                    "fix_events": int(event_counts.get((school_id, bssid), 0)),
                    "carried_observations": int(carried_counts.get((school_id, bssid), 0)),
                    "days_active": (
                        int(group["local_date"].nunique()) if "local_date" in group.columns else 1
                    ),
                    "first_seen_utc": group["created_timestamp"].min(),
                    "last_seen_utc": group["created_timestamp"].max(),
                    "avg_signal_dbm": (
                        round(float(group["wifi_signal_dbm"].mean()), 2)
                        if "wifi_signal_dbm" in group.columns and group["wifi_signal_dbm"].notna().any()
                        else np.nan
                    ),
                    "operational_hours_obs": op_obs,
                    "out_of_hours_obs": total_obs - op_obs,
                    "pct_operational_hours": round((op_obs / total_obs) * 100.0, 1),
                    "avg_accuracy_radius_m": (
                        round(float(group["detected_location_accuracy"].mean()), 2)
                        if "detected_location_accuracy" in group.columns
                        else np.nan
                    ),
                    "coord_tuples": coord_tuples,
                    "coord_pair_count": len(coord_tuples),
                }
            )

        return (
            pd.DataFrame(profiles)
            .sort_values(by=["school_id_giga", "total_observations"], ascending=[True, False])
            .reset_index(drop=True)
        )

    # ------------------------------------------------------------------
    # Facility observation clusters
    # ------------------------------------------------------------------
    def _anchor_window_events(self) -> pd.DataFrame:
        events = self.fix_events
        if events.empty:
            return events.copy()
        mask = events["is_workday"].astype(bool)
        if "is_operational_hours" in events.columns:
            mask &= events["is_operational_hours"].fillna(False).astype(bool)
        return events[mask].copy()

    def _cluster_facility(
        self, events: pd.DataFrame, school_name: Any
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        cfg = self.config
        events = events.copy()
        events["facility_cluster_id"] = dbscan_labels(
            events["detected_latitude"], events["detected_longitude"], cfg.anchor_eps_m, 1
        )
        events["_device_day"] = list(zip(events["device_id"], events["local_date"]))
        ssid_match = {
            ssid: ssid_matches_name([ssid], school_name, cfg)
            for ssid in events["detected_wifi_ssid"].dropna().unique()
        }
        events["_name_match"] = events["detected_wifi_ssid"].map(ssid_match).fillna(False).astype(bool)
        accuracy = events.get("detected_location_accuracy")

        rows = []
        for cluster_id, group in events.groupby("facility_cluster_id"):
            lat, lon = weighted_centroid(
                group["detected_latitude"],
                group["detected_longitude"],
                accuracy.loc[group.index] if accuracy is not None else None,
                cfg.accuracy_floor_m,
            )
            ssids = _unique_values(group["detected_wifi_ssid"])
            bssids = _unique_values(group["detected_wifi_bssid"])
            hotspot = group["is_mobile_hotspot"] if "is_mobile_hotspot" in group else pd.Series(False, index=group.index)
            rows.append(
                {
                    "facility_cluster_id": int(cluster_id),
                    "centroid_lat": lat,
                    "centroid_lon": lon,
                    "device_days": int(group["_device_day"].nunique()),
                    "devices": int(group["device_id"].nunique()),
                    "events": int(len(group)),
                    "first_date": group["local_date"].min(),
                    "last_date": group["local_date"].max(),
                    "bssids": bssids,
                    "ssids": ssids,
                    "device_ids": _unique_values(group["device_id"]),
                    "hotspot_share": round(float(hotspot.astype(bool).mean()), 3),
                    "mean_accuracy_m": (
                        round(float(pd.to_numeric(accuracy.loc[group.index]).mean()), 2)
                        if accuracy is not None
                        else np.nan
                    ),
                    "name_match_device_days": int(
                        group.loc[group["_name_match"], "_device_day"].nunique()
                    ),
                }
            )
        clusters = pd.DataFrame(rows).set_index("facility_cluster_id", drop=False)
        clusters.index.name = None
        clusters["is_supported"] = clusters["device_days"] >= cfg.min_support_device_days
        clusters["is_hotspot_cluster"] = clusters["hotspot_share"] >= cfg.hotspot_share_min
        clusters["ssid_name_match"] = (
            clusters["name_match_device_days"] >= cfg.min_support_device_days
        )
        return clusters, events.drop(columns=["_device_day", "_name_match"])

    @staticmethod
    def _rank(clusters: pd.DataFrame, support: Optional[pd.Series] = None) -> pd.DataFrame:
        ranked = clusters.copy()
        ranked["_support"] = support if support is not None else ranked["device_days"]
        return ranked.sort_values(
            by=["_support", "devices", "events", "facility_cluster_id"],
            ascending=[False, False, False, True],
        )

    def _candidate_pool(self, clusters: pd.DataFrame) -> pd.DataFrame:
        pool = clusters[clusters["is_supported"]]
        if pool.empty:
            pool = clusters
        fixed = pool[~pool["is_hotspot_cluster"]]
        return fixed if not fixed.empty else pool

    def _select_candidates(
        self,
        pool: pd.DataFrame,
        cluster_events: pd.DataFrame,
        govt: Tuple[float, float],
        eligible_event_ids: Optional[set],
    ) -> Tuple[Dict[str, int], Dict[str, str]]:
        cfg = self.config
        dominance = int(self._rank(pool).index[0])
        candidates: Dict[str, int] = {}
        fallbacks: Dict[str, str] = {}

        for strategy in cfg.strategies:
            if strategy == STRATEGY_TELEMETRY_DOMINANCE:
                candidates[strategy] = dominance
            elif strategy == STRATEGY_GOVT_PROXIMITY:
                if pd.isna(govt[0]) or pd.isna(govt[1]):
                    candidates[strategy], fallbacks[strategy] = dominance, FALLBACK_NO_GOVT_PIN
                    continue
                in_range = pool[pool["dist_to_govt_m"] <= cfg.govt_anchor_radius_m]
                if in_range.empty:
                    candidates[strategy], fallbacks[strategy] = dominance, FALLBACK_NO_CLUSTER_IN_RADIUS
                    continue
                ranked = in_range.assign(_support=in_range["device_days"]).sort_values(
                    by=["_support", "devices", "events", "dist_to_govt_m"],
                    ascending=[False, False, False, True],
                )
                candidates[strategy] = int(ranked.index[0])
            elif strategy == STRATEGY_STATIONARY_FIRST:
                if eligible_event_ids is None:
                    candidates[strategy], fallbacks[strategy] = dominance, FALLBACK_NO_DEVICE_CLASSES
                    continue
                eligible = cluster_events[cluster_events["fix_event_id"].isin(eligible_event_ids)]
                support = (
                    eligible.assign(_dd=list(zip(eligible["device_id"], eligible["local_date"])))
                    .groupby("facility_cluster_id")["_dd"]
                    .nunique()
                    .reindex(pool.index)
                    .fillna(0)
                )
                if (support > 0).sum() == 0:
                    candidates[strategy], fallbacks[strategy] = dominance, FALLBACK_NO_STATIONARY_EVIDENCE
                    continue
                candidates[strategy] = int(self._rank(pool, support).index[0])
        return candidates, fallbacks

    @staticmethod
    def _resolve(
        candidates: Dict[str, int], clusters: pd.DataFrame
    ) -> Tuple[Optional[int], bool, str]:
        distinct = sorted(set(candidates.values()))
        if len(distinct) == 1:
            resolved_by = RESOLVED_BY_AGREEMENT if len(candidates) > 1 else RESOLVED_BY_SINGLE_STRATEGY
            return distinct[0], True, resolved_by
        matched = [c for c in distinct if clusters.loc[c, "ssid_name_match"]]
        if len(matched) == 1:
            return matched[0], False, RESOLVED_BY_NAME_MATCH
        return None, False, RESOLVED_BY_UNRESOLVED

    @staticmethod
    def _eligible_event_ids(device_events: Optional[pd.DataFrame]) -> Optional[set]:
        if device_events is None:
            return None
        if device_events.empty:
            return set()
        stationary = device_events["mobility_class"] == "STATIONARY"
        commuter_home = (device_events["mobility_class"] == "COMMUTER") & device_events[
            "is_dominant_cluster"
        ].astype(bool)
        return set(device_events.loc[stationary | commuter_home, "fix_event_id"])

    def build_facility_spatial_summary(
        self, device_events: Optional[pd.DataFrame] = None
    ) -> pd.DataFrame:
        """
        Cluster each facility's anchor-window fix events and pick its anchor.

        Anchor-window events are non-carried fix events inside operational
        hours on configured workdays, from all devices, with or without a
        BSSID. DBSCAN uses `anchor_eps_m` and a minimum of one event, so
        every event belongs to a cluster and support decides which clusters
        count. Each configured strategy proposes one cluster; agreement,
        then a registry-name match, resolves the anchor. A cluster
        name-matches when SSIDs matching the registry name are seen on at
        least `min_support_device_days` of its device-days.

        Args:
            device_events: Output of `MobilityAnalyzer.build_device_event_table`.
                Needed only for the `stationary_first` strategy.

        Returns:
            One row per facility with anchor centroid
            (`empirical_centroid_lat`, `empirical_centroid_lon`), anchor
            support, strategy candidates, agreement, resolution, split
            distance between supported clusters, hotspot event share, and
            provenance. The anchor centroid is empty when the strategies
            disagree and no name match resolves them, or when the facility
            has no anchor-window events. Cluster details are kept on
            `self.facility_clusters` and labelled events on
            `self.facility_events`.
        """
        cfg = self.config
        eligible = self._eligible_event_ids(device_events)
        window_events = self._anchor_window_events()
        all_events = self.fix_events
        valid_rows = self.fix_event_rows

        summaries, cluster_tables, event_tables = [], [], []
        for school_id, rows in valid_rows.groupby("school_id_giga"):
            school_name = _first_valid(rows["school_name"]) if "school_name" in rows else np.nan
            govt = (
                _first_valid(rows["govt_latitude"]) if "govt_latitude" in rows else np.nan,
                _first_valid(rows["govt_longitude"]) if "govt_longitude" in rows else np.nan,
            )
            school_events = all_events[all_events["school_id_giga"] == school_id]
            facility_window = window_events[window_events["school_id_giga"] == school_id]

            summary = {
                "school_id_giga": school_id,
                "school_name": school_name if pd.notna(school_name) else school_id,
                "total_valid_geo_records": int(len(rows)),
                "ambient_scan_count": (
                    int(rows["detected_wifi_bssid"].isna().sum())
                    if "detected_wifi_bssid" in rows
                    else int(len(rows))
                ),
                "carried_scan_count": int(rows["fix_carried"].sum()),
                "distinct_devices": int(rows["device_id"].nunique()),
                "total_fix_events": int(len(school_events)),
                "anchor_window_events": int(len(facility_window)),
                "facility_device_days": int(
                    facility_window[["device_id", "local_date"]].drop_duplicates().shape[0]
                ),
                "govt_latitude": govt[0],
                "govt_longitude": govt[1],
                "hotspot_event_pct": (
                    round(float(school_events["is_mobile_hotspot"].mean()) * 100.0, 1)
                    if not school_events.empty
                    else 0.0
                ),
                "cluster_count": 0,
                "supported_cluster_count": 0,
                "split_distance_m": 0.0,
                "anchor_cluster_id": None,
                "anchor_supported": False,
                "anchor_support_device_days": 0,
                "anchor_support_devices": 0,
                "anchor_support_events": 0,
                "anchor_bssids": [],
                "anchor_ssids": [],
                "anchor_device_ids": [],
                "ssid_name_match": False,
                "empirical_centroid_lat": np.nan,
                "empirical_centroid_lon": np.nan,
                "mean_accuracy_m": np.nan,
                "govt_displacement_m": np.nan,
                "strategy_candidates": {},
                "candidate_govt_displacement_m": {},
                "strategy_agreement": False,
                "anchor_resolved_by": RESOLVED_BY_NO_CLUSTER,
                "strategy_fallback_reason": None,
                **cfg.provenance(),
            }

            if not facility_window.empty:
                clusters, labelled = self._cluster_facility(facility_window, school_name)
                clusters["dist_to_govt_m"] = (
                    haversine_m(clusters["centroid_lat"], clusters["centroid_lon"], govt[0], govt[1])
                    if pd.notna(govt[0]) and pd.notna(govt[1])
                    else np.nan
                )
                supported = clusters[clusters["is_supported"]]
                pool = self._candidate_pool(clusters)
                candidates, fallbacks = self._select_candidates(pool, labelled, govt, eligible)
                anchor_id, agreement, resolved_by = self._resolve(candidates, clusters)

                summary.update(
                    {
                        "cluster_count": int(len(clusters)),
                        "supported_cluster_count": int(len(supported)),
                        "split_distance_m": round(
                            max_pairwise_distance_m(supported["centroid_lat"], supported["centroid_lon"]),
                            1,
                        ),
                        "strategy_candidates": candidates,
                        "candidate_govt_displacement_m": {
                            s: (
                                round(float(clusters.loc[c, "dist_to_govt_m"]), 1)
                                if pd.notna(clusters.loc[c, "dist_to_govt_m"])
                                else None
                            )
                            for s, c in candidates.items()
                        },
                        "strategy_agreement": agreement,
                        "anchor_resolved_by": resolved_by,
                        "strategy_fallback_reason": (
                            "; ".join(f"{s}: {r}" for s, r in fallbacks.items()) or None
                        ),
                    }
                )
                if anchor_id is not None:
                    anchor = clusters.loc[anchor_id]
                    summary.update(
                        {
                            "anchor_cluster_id": int(anchor_id),
                            "anchor_supported": bool(anchor["is_supported"]),
                            "anchor_support_device_days": int(anchor["device_days"]),
                            "anchor_support_devices": int(anchor["devices"]),
                            "anchor_support_events": int(anchor["events"]),
                            "anchor_bssids": anchor["bssids"],
                            "anchor_ssids": anchor["ssids"],
                            "anchor_device_ids": anchor["device_ids"],
                            "ssid_name_match": bool(anchor["ssid_name_match"]),
                            "empirical_centroid_lat": float(anchor["centroid_lat"]),
                            "empirical_centroid_lon": float(anchor["centroid_lon"]),
                            "mean_accuracy_m": anchor["mean_accuracy_m"],
                            "govt_displacement_m": (
                                round(float(anchor["dist_to_govt_m"]), 1)
                                if pd.notna(anchor["dist_to_govt_m"])
                                else np.nan
                            ),
                        }
                    )
                labelled["is_anchor_cluster"] = labelled["facility_cluster_id"] == anchor_id
                clusters["is_anchor_cluster"] = clusters.index == anchor_id
                clusters["is_candidate"] = clusters.index.isin(set(candidates.values()))
                clusters.insert(0, "school_id_giga", school_id)
                cluster_tables.append(clusters.reset_index(drop=True))
                event_tables.append(labelled)

            summaries.append(summary)

        self.facility_clusters = (
            pd.concat(cluster_tables, ignore_index=True) if cluster_tables else pd.DataFrame()
        )
        self.facility_events = (
            pd.concat(event_tables, ignore_index=True) if event_tables else pd.DataFrame()
        )
        if not summaries:
            return pd.DataFrame()
        return (
            pd.DataFrame(summaries)
            .sort_values(by="total_valid_geo_records", ascending=False)
            .reset_index(drop=True)
        )

    # ------------------------------------------------------------------
    # Plots
    # ------------------------------------------------------------------
    def plot_signal_vs_accuracy_density(self) -> go.Figure:
        """
        Renders a 2D Scatter/Density plot mapping Wi-Fi Signal Strength (dBm)
        against Google API Precision Radius (meters).
        """
        signal_col = "wifi_signal_dbm"
        if signal_col not in self.df.columns or "detected_location_accuracy" not in self.df.columns:
            fig = go.Figure()
            fig.update_layout(title="Wi-Fi Signal vs Precision metrics unavailable in dataset")
            return fig

        plot_df = self.df[
            self.df[signal_col].notna() & self.df["detected_location_accuracy"].notna()
        ].copy()

        fig = px.scatter(
            plot_df,
            x=signal_col,
            y="detected_location_accuracy",
            color="is_mobile_hotspot",
            color_discrete_map={True: "#d62728", False: "#1f77b4"},
            opacity=0.6,
            labels={
                signal_col: "Wi-Fi Signal Strength (dBm)",
                "detected_location_accuracy": "Google API Precision Radius (meters)",
                "is_mobile_hotspot": "Consumer Mobile Hotspot",
            },
            title="Wi-Fi Signal Strength (dBm) vs Google API Location Precision Radius",
        )
        fig.update_layout(template="plotly_white", height=380, margin=dict(l=10, r=10, t=40, b=30))
        return fig

    def plot_bssid_temporal_profile(self, school_id_giga: str) -> go.Figure:
        """
        Renders a stacked bar chart showing Operational Hours (08:00-19:59) vs
        Out-of-Hours scan count for each BSSID registered to a facility.
        """
        profiles = self.build_bssid_profiles()
        if profiles.empty:
            fig = go.Figure()
            fig.update_layout(title="No active BSSIDs found for this facility")
            return fig

        fac_prof = profiles[profiles["school_id_giga"] == school_id_giga].copy()
        if fac_prof.empty:
            fig = go.Figure()
            fig.update_layout(title=f"No BSSID profiles recorded for {school_id_giga}")
            return fig

        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                y=fac_prof["detected_wifi_bssid"],
                x=fac_prof["operational_hours_obs"],
                name="Operational Hours (08:00-19:59)",
                orientation="h",
                marker=dict(color="#2ca02c"),
            )
        )
        fig.add_trace(
            go.Bar(
                y=fac_prof["detected_wifi_bssid"],
                x=fac_prof["out_of_hours_obs"],
                name="Out-of-Hours (20:00-07:59)",
                orientation="h",
                marker=dict(color="#d62728"),
            )
        )
        fig.update_layout(
            barmode="stack",
            title=f"BSSID Temporal Profile for Facility: {school_id_giga}",
            xaxis=dict(title="Observation Count"),
            yaxis=dict(title="BSSID MAC Address", autorange="reversed"),
            template="plotly_white",
            height=350,
            margin=dict(l=10, r=10, t=40, b=30),
        )
        return fig
