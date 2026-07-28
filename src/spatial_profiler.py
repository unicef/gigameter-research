"""
Module: src/spatial_profiler.py
Purpose: Spatial aggregation, BSSID fingerprinting, and coordinate tuple
         profiling for GigaMeter telemetry (Pillars 1, 2, and 3).
Rules: Aligned with GigaMeter Technical Specs v2.2.
"""

import pandas as pd
import numpy as np
from typing import Tuple, List, Dict, Any, Optional

from gigaspatial.processing import calculate_distance as haversine_distance_meters


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
    Spatial Analytics Engine for GigaMeter Telemetry.
    Computes BSSID fingerprinting profiles and facility-level spatial centroids.
    """

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

    def build_bssid_profiles(self) -> pd.DataFrame:
        """
        Pillar 2: BSSID-Level Infrastructure Profiling.
        Groups strictly by school and BSSID (ignoring NULL BSSIDs).
        Extracts coordinate tuples and computes temporal operational distributions.
        """
        # Filter for non-null BSSIDs
        bssid_df = self.df[self.df["detected_wifi_bssid"].notna()].copy()

        if bssid_df.empty:
            print("Warning: No valid BSSIDs found in dataset.")
            return pd.DataFrame()

        profiles = []
        grouped = bssid_df.groupby(["school_id_giga", "detected_wifi_bssid"])

        for (school_id, bssid), group in grouped:
            total_obs = len(group)
            operational_obs = int(group["is_operational_hours"].sum())
            out_of_hours_obs = total_obs - operational_obs

            coord_tuples = _extract_coord_tuples(group)
            ssid_series = group["detected_wifi_bssid"].dropna()

            profiles.append(
                {
                    "school_id_giga": school_id,
                    "detected_wifi_bssid": bssid,
                    "last_known_ssid": (
                        ssid_series.iloc[-1] if not ssid_series.empty else None
                    ),
                    "distinct_devices": int(group["device_id"].nunique()),
                    "total_observations": total_obs,
                    "days_active": (
                        int(group["local_date"].nunique())
                        if "local_date" in group.columns
                        else 1
                    ),
                    "first_seen_utc": group["created_timestamp"].min(),
                    "last_seen_utc": group["created_timestamp"].max(),
                    "avg_signal_dbm": (
                        round(float(group["wifi_signal_dbm"].mean()), 2)
                        if "wifi_signal_dbm" in group.columns
                        and group["wifi_signal_dbm"].notna().any()
                        else np.nan
                    ),
                    "operational_hours_obs": operational_obs,
                    "out_of_hours_obs": out_of_hours_obs,
                    "pct_operational_hours": round(
                        (operational_obs / total_obs) * 100.0, 1
                    ),
                    "avg_accuracy_radius_m": round(
                        float(group["detected_location_accuracy"].mean()), 2
                    ),
                    "coord_tuples": coord_tuples,
                    "coord_pair_count": len(coord_tuples),
                }
            )

        result_df = pd.DataFrame(profiles)
        return result_df.sort_values(
            by=["school_id_giga", "total_observations"], ascending=[True, False]
        ).reset_index(drop=True)

    def build_facility_spatial_summary(
        self, schools_df: Optional[pd.DataFrame] = None
    ) -> pd.DataFrame:
        """
        Pillars 1 & 3: Facility-Level Spatial Centroids & Displacement.
        Uses ALL valid API coordinates (including ambient scans where BSSID is NULL).
        Calculates accuracy-weighted spatial centroids and displacement vs government pins.
        """
        valid_geo = self.df[
            self.df["detected_latitude"].notna() & self.df["detected_longitude"].notna()
        ].copy()

        if valid_geo.empty:
            print("Warning: No valid coordinate records found.")
            return pd.DataFrame()

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

                # Drop existing govt columns to prevent suffix collisions (_x, _y)
                valid_geo = valid_geo.drop(
                    columns=[
                        c
                        for c in ["govt_latitude", "govt_longitude"]
                        if c in valid_geo.columns
                    ]
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

        # -------------------------------------------------------------------
        # Step 2: Calculate Weighted Centroids and Facility Summaries
        # -------------------------------------------------------------------

        summaries = []
        grouped = valid_geo.groupby("school_id_giga")

        for school_id, group in grouped:
            lats = group["detected_latitude"].values
            lons = group["detected_longitude"].values
            accuracies = group["detected_location_accuracy"].values

            # Accuracy-Weighted Spatial Centroid: w_i = 1 / (accuracy_i^2)
            weights = 1.0 / np.square(np.maximum(accuracies, 1.0))
            weighted_lat = float(np.sum(lats * weights) / np.sum(weights))
            weighted_lon = float(np.sum(lons * weights) / np.sum(weights))

            coord_tuples = _extract_coord_tuples(group)

            # Identify official government coordinates for this facility
            govt_lat = group["govt_latitude"].dropna().iloc[0]
            govt_lon = group["govt_longitude"].dropna().iloc[0]

            # Compute Haversine Displacement against Government Registry Pin
            govt_disp_m = haversine_distance_meters(
                weighted_lat, weighted_lon, govt_lat, govt_lon
            )

            summaries.append(
                {
                    "school_id_giga": school_id,
                    "total_valid_geo_records": len(group),
                    "ambient_scan_count": int(
                        group["detected_wifi_bssid"].isna().sum()
                    ),
                    "bssid_scan_count": int(group["detected_wifi_bssid"].notna().sum()),
                    "distinct_devices": int(group["device_id"].nunique()),
                    "empirical_centroid_lat": weighted_lat,
                    "empirical_centroid_lon": weighted_lon,
                    "govt_latitude": govt_lat,
                    "govt_longitude": govt_lon,
                    "govt_displacement_m": (
                        round(govt_disp_m, 2) if pd.notna(govt_disp_m) else np.nan
                    ),
                    "mean_accuracy_m": round(
                        float(group["detected_location_accuracy"].mean()), 2
                    ),
                    "coord_tuples": coord_tuples,
                }
            )

        summary_df = pd.DataFrame(summaries)
        return summary_df.sort_values(by="total_valid_geo_records", ascending=False)
