"""
Module: src/spatial_profiler.py
Purpose: Spatial aggregation, BSSID fingerprinting, mobile hotspot detection,
         and strategy-driven facility centroid resolution for GigaMeter telemetry.
Rules: Aligned with GigaMeter Data Dictionary v2.2 (Pillars 1, 2, and 3).
"""

import pandas as pd
import numpy as np
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union
import plotly.express as px
import plotly.graph_objects as go

from gigaspatial.processing import calculate_distance as haversine_distance_meters

from src.utils.data_loader import TelemetryLoader


class ClusterResolutionStrategy(Enum):
    """Primary Cluster Selection Strategies for BSSID Splits (> 2km)."""

    TELEMETRY_DOMINANCE = (
        "telemetry_dominance"  # Unbiased: Selects cluster with max operational scans
    )
    GOVT_PROXIMITY_ANCHOR = (
        "govt_proximity_anchor"  # Prior-Informed: Uses govt pin as tie-breaker (<= 2km)
    )
    STATIONARY_FIRST = (
        "stationary_first"  # Hardware-First: Prefers stationary hardware clusters
    )


def _extract_coord_tuples(df_subset: pd.DataFrame) -> List[Tuple[float, float]]:
    """Extracts valid (latitude, longitude) coordinate tuples from a DataFrame subset."""
    valid_mask = (
        df_subset["detected_latitude"].notna() & df_subset["detected_longitude"].notna()
    )
    valid_coords = df_subset.loc[
        valid_mask, ["detected_latitude", "detected_longitude"]
    ]
    return [tuple(x) for x in valid_coords.to_numpy()]


class SpatialProfiler:
    """
    Spatial Analytics & BSSID Fingerprinting Engine for GigaMeter Telemetry.
    Includes consumer mobile hotspot regex detection, multi-day spatial drift checks,
    and configurable primary cluster resolution strategies.
    """

    HOTSPOT_REGEX_PATTERN = (
        r"(?i)(iphone|android|galaxy|hotspot|teacher|pixel|redmi|tether|"
        r"samsung|huawei|oppo|vivo|xiaomi|realme|mobicom|unitel|mifi)"
    )

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
    ) -> None:
        """
        Load a canonical telemetry frame and tag mobile hotspots.

        Provide exactly one of `telemetry_df`, `file_path`, or `query_name`.
        School-pin merge and local-time enrichment are performed by
        `TelemetryLoader` before hotspot tagging. `is_operational_hours` is
        read from that frame.

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
        """
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

    def _tag_mobile_hotspots(self) -> None:
        """
        Detects consumer mobile hotspots via:
        1. Case-insensitive SSID regex pattern matching.
        2. BSSID multi-day spatial drift (> 1000m across active days).
        """
        ssid_col = "detected_wifi_ssid"
        bssid_col = "detected_wifi_bssid"

        # 1. Regex SSID pattern match
        if ssid_col in self.df.columns:
            self.df["is_hotspot_ssid"] = (
                self.df[ssid_col]
                .astype(str)
                .str.contains(self.HOTSPOT_REGEX_PATTERN, regex=True, na=False)
            )
        else:
            self.df["is_hotspot_ssid"] = False

        # 2. Multi-day spatial drift check
        hotspot_bssids = set()
        if bssid_col in self.df.columns and "local_date" in self.df.columns:
            valid_bssid_df = self.df[
                self.df[bssid_col].notna()
                & self.df["detected_latitude"].notna()
                & self.df["detected_longitude"].notna()
            ]

            bssid_daily = (
                valid_bssid_df.groupby([bssid_col, "local_date"])
                .agg(
                    mean_lat=("detected_latitude", "mean"),
                    mean_lon=("detected_longitude", "mean"),
                )
                .reset_index()
            )

            for bssid, group in bssid_daily.groupby(bssid_col):
                if len(group) > 1:
                    lats, lons = group["mean_lat"].values, group["mean_lon"].values
                    max_drift = max(
                        haversine_distance_meters(lats[i], lons[i], lats[j], lons[j])
                        for i in range(len(lats))
                        for j in range(i + 1, len(lats))
                    )
                    if max_drift > 1000.0:  # Drift > 1km
                        hotspot_bssids.add(bssid)

        self.df["is_hotspot_drift"] = (
            self.df[bssid_col].isin(hotspot_bssids)
            if bssid_col in self.df.columns
            else False
        )
        self.df["is_mobile_hotspot"] = (
            self.df["is_hotspot_ssid"] | self.df["is_hotspot_drift"]
        )

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
        if (
            "detected_wifi_bssid" in self.df.columns
            and total_records > 0
        ):
            ambient_scans = int(self.df["detected_wifi_bssid"].isna().sum())
        else:
            ambient_scans = 0
        ambient_pct = (
            round((ambient_scans / total_records) * 100.0, 1)
            if total_records > 0
            else 0.0
        )

        if "detected_location_accuracy" in self.df.columns and total_records > 0:
            mean_accuracy_m = round(
                float(self.df["detected_location_accuracy"].mean()), 1
            )
        else:
            mean_accuracy_m = 0.0

        if "is_operational_hours" in self.df.columns and total_records > 0:
            operational_hours_pct = round(
                (self.df["is_operational_hours"].sum() / total_records) * 100.0, 1
            )
        else:
            operational_hours_pct = 100.0

        if "is_mobile_hotspot" in self.df.columns and total_records > 0:
            hotspot_scans = int(self.df["is_mobile_hotspot"].sum())
        else:
            hotspot_scans = 0
        hotspot_pct = (
            round((hotspot_scans / total_records) * 100.0, 1)
            if total_records > 0
            else 0.0
        )

        return {
            "total_records": total_records,
            "ambient_scans": ambient_scans,
            "ambient_pct": ambient_pct,
            "mean_accuracy_m": mean_accuracy_m,
            "operational_hours_pct": operational_hours_pct,
            "hotspot_scans": hotspot_scans,
            "hotspot_pct": hotspot_pct,
        }

    def build_bssid_profiles(self) -> pd.DataFrame:
        """
        Pillar 2: BSSID-Level Infrastructure Profiling.
        Groups strictly by school and non-null BSSIDs.
        Extracts coordinate tuples and operational hours distributions.
        """
        bssid_col = "detected_wifi_bssid"
        ssid_col = "detected_wifi_ssid"
        signal_col = "wifi_signal_dbm"
        if bssid_col not in self.df.columns:
            return pd.DataFrame()

        bssid_df = self.df[self.df[bssid_col].notna()].copy()
        if bssid_df.empty:
            return pd.DataFrame()

        profiles = []
        grouped = bssid_df.groupby(["school_id_giga", bssid_col])

        for (school_id, bssid), group in grouped:
            total_obs = len(group)
            op_obs = int(group["is_operational_hours"].sum())
            coord_tuples = _extract_coord_tuples(group)

            profiles.append(
                {
                    "school_id_giga": school_id,
                    "detected_wifi_bssid": bssid,
                    "last_known_ssid": (
                        group[ssid_col].dropna().iloc[-1]
                        if ssid_col in group.columns
                        and not group[ssid_col].dropna().empty
                        else None
                    ),
                    "is_mobile_hotspot": bool(group["is_mobile_hotspot"].any()),
                    "distinct_devices": (
                        int(group["device_id"].nunique())
                        if "device_id" in group.columns
                        else 1
                    ),
                    "total_observations": total_obs,
                    "days_active": (
                        int(group["local_date"].nunique())
                        if "local_date" in group.columns
                        else 1
                    ),
                    "first_seen_utc": (
                        group["created_timestamp"].min()
                        if "created_timestamp" in group.columns
                        else None
                    ),
                    "last_seen_utc": (
                        group["created_timestamp"].max()
                        if "created_timestamp" in group.columns
                        else None
                    ),
                    "avg_signal_dbm": (
                        round(float(group[signal_col].mean()), 2)
                        if signal_col in group.columns
                        and group[signal_col].notna().any()
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
            .sort_values(
                by=["school_id_giga", "total_observations"], ascending=[True, False]
            )
            .reset_index(drop=True)
        )

    def build_facility_spatial_summary(
        self,
        strategy: ClusterResolutionStrategy = ClusterResolutionStrategy.GOVT_PROXIMITY_ANCHOR,
    ) -> pd.DataFrame:
        """
        Resolve an empirical facility centroid for each school.

        Uses valid API coordinates and the chosen strategy when BSSID splits
        exceed 2 km. Official pins are read from `govt_latitude` and
        `govt_longitude` already merged onto the telemetry frame.

        Args:
            strategy: Primary cluster selection mode for BSSID splits.

        Returns:
            One row per school with centroid, government displacement, and
            hotspot diagnostics. Empty when no valid coordinates remain.
        """
        # Strict No-IP Fallback: Filter out null coordinates
        valid_geo = self.df[
            self.df["detected_latitude"].notna() & self.df["detected_longitude"].notna()
        ].copy()

        if valid_geo.empty:
            return pd.DataFrame()

        if "detected_wifi_bssid" not in valid_geo.columns:
            valid_geo["detected_wifi_bssid"] = np.nan
        bssid_col = "detected_wifi_bssid"

        summaries = []
        for school_id, group in valid_geo.groupby("school_id_giga"):
            govt_lat = (
                group["govt_latitude"].dropna().iloc[0]
                if "govt_latitude" in group.columns
                and not group["govt_latitude"].dropna().empty
                else np.nan
            )
            govt_lon = (
                group["govt_longitude"].dropna().iloc[0]
                if "govt_longitude" in group.columns
                and not group["govt_longitude"].dropna().empty
                else np.nan
            )

            # Group scans by BSSID to evaluate spatial clusters
            bssid_clusters = []
            for bssid, b_group in group.groupby(bssid_col, dropna=False):
                lats, lons = (
                    b_group["detected_latitude"].values,
                    b_group["detected_longitude"].values,
                )
                accs = (
                    b_group["detected_location_accuracy"].values
                    if "detected_location_accuracy" in b_group.columns
                    else np.ones(len(b_group)) * 20.0
                )
                weights = 1.0 / np.square(np.maximum(accs, 1.0))

                c_lat = float(np.sum(lats * weights) / np.sum(weights))
                c_lon = float(np.sum(lons * weights) / np.sum(weights))
                op_scans = int(b_group["is_operational_hours"].sum())

                bssid_clusters.append(
                    {
                        "bssid": bssid,
                        "centroid_lat": c_lat,
                        "centroid_lon": c_lon,
                        "op_scans": op_scans,
                        "total_scans": len(b_group),
                        "is_hotspot": bool(b_group["is_mobile_hotspot"].any()),
                    }
                )

            clusters_df = pd.DataFrame(bssid_clusters)

            # Evaluate max pairwise BSSID distance
            max_bssid_dist_m = 0.0
            if len(clusters_df) > 1:
                c_lats, c_lons = (
                    clusters_df["centroid_lat"].values,
                    clusters_df["centroid_lon"].values,
                )
                max_bssid_dist_m = max(
                    haversine_distance_meters(
                        c_lats[i], c_lons[i], c_lats[j], c_lons[j]
                    )
                    for i in range(len(c_lats))
                    for j in range(i + 1, len(c_lats))
                )

            # -------------------------------------------------------------------
            # Primary Cluster Selection Strategy Engine
            # -------------------------------------------------------------------
            selected_cluster = None

            if (
                strategy == ClusterResolutionStrategy.GOVT_PROXIMITY_ANCHOR
                and pd.notna(govt_lat)
            ):
                # Filter clusters within 2km of Government Pin
                clusters_df["dist_to_govt_m"] = clusters_df.apply(
                    lambda r: haversine_distance_meters(
                        r["centroid_lat"], r["centroid_lon"], govt_lat, govt_lon
                    ),
                    axis=1,
                )
                prox_candidates = clusters_df[clusters_df["dist_to_govt_m"] <= 2000.0]
                if not prox_candidates.empty:
                    selected_cluster = prox_candidates.sort_values(
                        by="op_scans", ascending=False
                    ).iloc[0]

            if selected_cluster is None:
                # Fallback / Unbiased Strategy: Max operational scans (excluding mobile hotspots if fixed exists)
                fixed_clusters = clusters_df[~clusters_df["is_hotspot"]]
                target_pool = (
                    fixed_clusters if not fixed_clusters.empty else clusters_df
                )
                selected_cluster = target_pool.sort_values(
                    by="op_scans", ascending=False
                ).iloc[0]

            # Compute empirical facility location based on selected primary cluster
            primary_bssid = selected_cluster["bssid"]
            primary_records = (
                group[group[bssid_col] == primary_bssid]
                if pd.notna(primary_bssid)
                else group
            )

            p_lats = primary_records["detected_latitude"].values
            p_lons = primary_records["detected_longitude"].values
            p_accs = (
                primary_records["detected_location_accuracy"].values
                if "detected_location_accuracy" in primary_records.columns
                else np.ones(len(primary_records)) * 20.0
            )
            p_weights = 1.0 / np.square(np.maximum(p_accs, 1.0))

            empirical_lat = float(np.sum(p_lats * p_weights) / np.sum(p_weights))
            empirical_lon = float(np.sum(p_lons * p_weights) / np.sum(p_weights))

            govt_disp_m = haversine_distance_meters(
                empirical_lat, empirical_lon, govt_lat, govt_lon
            )
            hotspot_scan_pct = round(
                (group["is_mobile_hotspot"].sum() / len(group)) * 100.0, 1
            )

            summaries.append(
                {
                    "school_id_giga": school_id,
                    "school_name": (
                        group["school_name"].iloc[0]
                        if "school_name" in group.columns
                        else school_id
                    ),
                    "total_valid_geo_records": len(group),
                    "ambient_scan_count": (
                        int(group[bssid_col].isna().sum())
                        if bssid_col in group.columns
                        else 0
                    ),
                    "distinct_devices": (
                        int(group["device_id"].nunique())
                        if "device_id" in group.columns
                        else 1
                    ),
                    "empirical_centroid_lat": empirical_lat,
                    "empirical_centroid_lon": empirical_lon,
                    "govt_latitude": govt_lat,
                    "govt_longitude": govt_lon,
                    "govt_displacement_m": (
                        round(govt_disp_m, 2) if pd.notna(govt_disp_m) else np.nan
                    ),
                    "max_bssid_dist_m": round(max_bssid_dist_m, 2),
                    "hotspot_scan_pct": hotspot_scan_pct,
                    "resolution_strategy_used": strategy.value,
                    "mean_accuracy_m": round(float(np.mean(p_accs)), 2),
                    "coord_tuples": _extract_coord_tuples(group),
                }
            )

        return (
            pd.DataFrame(summaries)
            .sort_values(by="total_valid_geo_records", ascending=False)
            .reset_index(drop=True)
        )

    def plot_signal_vs_accuracy_density(self) -> go.Figure:
        """
        Renders a 2D Scatter/Density plot mapping Wi-Fi Signal Strength (dBm)
        against Google API Precision Radius (meters).
        """
        signal_col = "wifi_signal_dbm"
        if (
            signal_col not in self.df.columns
            or "detected_location_accuracy" not in self.df.columns
        ):
            fig = go.Figure()
            fig.update_layout(
                title="Wi-Fi Signal vs Precision metrics unavailable in dataset"
            )
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
        fig.update_layout(
            template="plotly_white", height=380, margin=dict(l=10, r=10, t=40, b=30)
        )
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
