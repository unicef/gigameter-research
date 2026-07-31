"""
Module: src/spatial_profiler.py
Purpose: Spatial aggregation, BSSID fingerprinting, mobile hotspot detection,
         and strategy-driven facility centroid resolution for GigaMeter telemetry.
Rules: Aligned with GigaMeter Data Dictionary v2.2 (Pillars 1, 2, and 3).
"""

import re
import pandas as pd
import numpy as np
from enum import Enum
from typing import Tuple, List, Dict, Any, Optional

from gigaspatial.processing import calculate_distance as haversine_distance_meters


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

    def __init__(self, telemetry_df: pd.DataFrame):
        self.df = telemetry_df.copy()

        # Standardize primary identifiers
        if "giga_id_school" in self.df.columns:
            self.df = self.df.rename(columns={"giga_id_school": "school_id_giga"})
        if "device_hardware_id" in self.df.columns:
            self.df = self.df.rename(columns={"device_hardware_id": "device_id"})

        # Ensure operational hours flag exists (08:00 - 19:59 local device time)
        if "is_operational_hours" not in self.df.columns:
            if "local_hour" in self.df.columns:
                self.df["is_operational_hours"] = self.df["local_hour"].between(8, 19)
            else:
                self.df["is_operational_hours"] = True  # Default fallback

        # Tag mobile hotspots and tethered connections
        self._tag_mobile_hotspots()

    def _tag_mobile_hotspots(self) -> None:
        """
        Detects consumer mobile hotspots via:
        1. Case-insensitive SSID regex pattern matching.
        2. BSSID multi-day spatial drift (> 1000m across active days).
        """
        ssid_col = (
            "detected_wifi_ssid"
            if "detected_wifi_ssid" in self.df.columns
            else "detected_ssid"
        )
        bssid_col = (
            "detected_wifi_bssid"
            if "detected_wifi_bssid" in self.df.columns
            else "detected_bssid"
        )

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

    def build_bssid_profiles(self) -> pd.DataFrame:
        """
        Pillar 2: BSSID-Level Infrastructure Profiling.
        Groups strictly by school and non-null BSSIDs.
        Extracts coordinate tuples and operational hours distributions.
        """
        bssid_col = (
            "detected_wifi_bssid"
            if "detected_wifi_bssid" in self.df.columns
            else "detected_bssid"
        )
        ssid_col = (
            "detected_wifi_ssid"
            if "detected_wifi_ssid" in self.df.columns
            else "detected_ssid"
        )
        signal_col = (
            "wifi_signal_dbm"
            if "wifi_signal_dbm" in self.df.columns
            else "detected_wifi_signal"
        )

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
        schools_df: Optional[pd.DataFrame] = None,
        strategy: ClusterResolutionStrategy = ClusterResolutionStrategy.GOVT_PROXIMITY_ANCHOR,
    ) -> pd.DataFrame:
        """
        Pillars 1, 2 & 3: Strategy-Driven Facility Centroid Engine.
        Uses valid API coordinates and resolves BSSID splits (> 2km) using the chosen strategy.
        """
        # Strict No-IP Fallback: Filter out null coordinates
        valid_geo = self.df[
            self.df["detected_latitude"].notna() & self.df["detected_longitude"].notna()
        ].copy()

        if valid_geo.empty:
            return pd.DataFrame()

        bssid_col = (
            "detected_wifi_bssid"
            if "detected_wifi_bssid" in valid_geo.columns
            else "detected_bssid"
        )

        # -------------------------------------------------------------------
        # Step 1: Resolve Official Government Coordinates
        # -------------------------------------------------------------------
        # Option A: Merge explicitly provided schools_df
        if schools_df is not None and not schools_df.empty:
            s_df = schools_df.copy()
            if "giga_id_school" in s_df.columns:
                s_df = s_df.rename(columns={"giga_id_school": "school_id_giga"})
            gov_cols = [
                c
                for c in [
                    "school_id_giga",
                    "latitude",
                    "longitude",
                    "govt_latitude",
                    "govt_longitude",
                ]
                if c in s_df.columns
            ]

            if "school_id_giga" in gov_cols:
                s_subset = (
                    s_df[gov_cols].drop_duplicates(subset=["school_id_giga"]).copy()
                )
                if (
                    "latitude" in s_subset.columns
                    and "govt_latitude" not in s_subset.columns
                ):
                    s_subset = s_subset.rename(
                        columns={
                            "latitude": "govt_latitude",
                            "longitude": "govt_longitude",
                        }
                    )

                valid_geo = valid_geo.drop(
                    columns=[
                        c
                        for c in ["govt_latitude", "govt_longitude"]
                        if c in valid_geo.columns
                    ],
                    errors="ignore",
                )
                valid_geo = valid_geo.merge(
                    s_subset[["school_id_giga", "govt_latitude", "govt_longitude"]],
                    on="school_id_giga",
                    how="left",
                )

        # Option B: Map pre-existing `latitude`/`longitude` in self.df if govt_latitude is missing
        if "govt_latitude" not in valid_geo.columns and "latitude" in valid_geo.columns:
            valid_geo = valid_geo.rename(
                columns={"latitude": "govt_latitude", "longitude": "govt_longitude"}
            )

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

    # def build_facility_spatial_summary(
    #     self, schools_df: Optional[pd.DataFrame] = None
    # ) -> pd.DataFrame:
    #     """
    #     Pillars 1 & 3: Facility-Level Spatial Centroids & Displacement.
    #     Uses ALL valid API coordinates (including ambient scans where BSSID is NULL).
    #     Calculates accuracy-weighted spatial centroids and displacement vs government pins.
    #     """
    #     valid_geo = self.df[
    #         self.df["detected_latitude"].notna() & self.df["detected_longitude"].notna()
    #     ].copy()

    #     if valid_geo.empty:
    #         print("Warning: No valid coordinate records found.")
    #         return pd.DataFrame()

    #     # -------------------------------------------------------------------
    #     # Step 1: Resolve Official Government Coordinates
    #     # -------------------------------------------------------------------
    #     # Option A: Merge explicitly provided schools_df
    #     if schools_df is not None and not schools_df.empty:
    #         s_df = schools_df.copy()
    #         if "giga_id_school" in s_df.columns:
    #             s_df = s_df.rename(columns={"giga_id_school": "school_id_giga"})

    #         gov_cols = [
    #             c
    #             for c in [
    #                 "school_id_giga",
    #                 "latitude",
    #                 "longitude",
    #                 "govt_latitude",
    #                 "govt_longitude",
    #             ]
    #             if c in s_df.columns
    #         ]

    #         if "school_id_giga" in gov_cols:
    #             s_subset = (
    #                 s_df[gov_cols].drop_duplicates(subset=["school_id_giga"]).copy()
    #             )
    #             if (
    #                 "latitude" in s_subset.columns
    #                 and "govt_latitude" not in s_subset.columns
    #             ):
    #                 s_subset = s_subset.rename(
    #                     columns={
    #                         "latitude": "govt_latitude",
    #                         "longitude": "govt_longitude",
    #                     }
    #                 )

    #             # Drop existing govt columns to prevent suffix collisions (_x, _y)
    #             valid_geo = valid_geo.drop(
    #                 columns=[
    #                     c
    #                     for c in ["govt_latitude", "govt_longitude"]
    #                     if c in valid_geo.columns
    #                 ]
    #             )
    #             valid_geo = valid_geo.merge(
    #                 s_subset[["school_id_giga", "govt_latitude", "govt_longitude"]],
    #                 on="school_id_giga",
    #                 how="left",
    #             )

    #     # Option B: Map pre-existing `latitude`/`longitude` in self.df if govt_latitude is missing
    #     if "govt_latitude" not in valid_geo.columns and "latitude" in valid_geo.columns:
    #         valid_geo = valid_geo.rename(
    #             columns={"latitude": "govt_latitude", "longitude": "govt_longitude"}
    #         )

    #     # -------------------------------------------------------------------
    #     # Step 2: Calculate Weighted Centroids and Facility Summaries
    #     # -------------------------------------------------------------------

    #     summaries = []
    #     grouped = valid_geo.groupby("school_id_giga")

    #     for school_id, group in grouped:
    #         lats = group["detected_latitude"].values
    #         lons = group["detected_longitude"].values
    #         accuracies = group["detected_location_accuracy"].values

    #         # Accuracy-Weighted Spatial Centroid: w_i = 1 / (accuracy_i^2)
    #         weights = 1.0 / np.square(np.maximum(accuracies, 1.0))
    #         weighted_lat = float(np.sum(lats * weights) / np.sum(weights))
    #         weighted_lon = float(np.sum(lons * weights) / np.sum(weights))

    #         coord_tuples = _extract_coord_tuples(group)

    #         # Identify official government coordinates for this facility
    #         govt_lat = group["govt_latitude"].dropna().iloc[0]
    #         govt_lon = group["govt_longitude"].dropna().iloc[0]

    #         # Compute Haversine Displacement against Government Registry Pin
    #         govt_disp_m = haversine_distance_meters(
    #             weighted_lat, weighted_lon, govt_lat, govt_lon
    #         )

    #         summaries.append(
    #             {
    #                 "school_id_giga": school_id,
    #                 "total_valid_geo_records": len(group),
    #                 "ambient_scan_count": int(
    #                     group["detected_wifi_bssid"].isna().sum()
    #                 ),
    #                 "bssid_scan_count": int(group["detected_wifi_bssid"].notna().sum()),
    #                 "distinct_devices": int(group["device_id"].nunique()),
    #                 "empirical_centroid_lat": weighted_lat,
    #                 "empirical_centroid_lon": weighted_lon,
    #                 "govt_latitude": govt_lat,
    #                 "govt_longitude": govt_lon,
    #                 "govt_displacement_m": (
    #                     round(govt_disp_m, 2) if pd.notna(govt_disp_m) else np.nan
    #                 ),
    #                 "mean_accuracy_m": round(
    #                     float(group["detected_location_accuracy"].mean()), 2
    #                 ),
    #                 "coord_tuples": coord_tuples,
    #             }
    #         )

    #     summary_df = pd.DataFrame(summaries)
    #     return summary_df.sort_values(by="total_valid_geo_records", ascending=False)
