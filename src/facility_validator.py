"""
Module: src/facility_validator.py
Purpose: Consolidated Facility Location Truth Engine, Composite Confidence Scoring (0-100),
         BSSID Coherence Penalty, Government Data Validation, and Plotly Dashboards.
Rules: Aligned with GigaMeter Data Dictionary v2.2 (08:00 - 19:59 Operational Window).
"""

import numpy as np
import pandas as pd
from typing import Optional, Dict, Any
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from src.spatial_profiler import (
    SpatialProfiler,
    haversine_distance_meters,
    ClusterResolutionStrategy,
)
from src.mobility_analyzer import MobilityAnalyzer


class FacilityValidator:
    """
    Facility Location Truth & Validation Engine for GigaMeter Telemetry.
    Computes a 5-factor location confidence score (0-100), applies the BSSID Coherence
    Penalty for spatial splits (> 2km), and classifies displacement against government records.
    """

    def __init__(
        self,
        telemetry_df: pd.DataFrame,
        schools_df: Optional[pd.DataFrame] = None,
        geofence_radius_m: float = 200.0,
        strategy: ClusterResolutionStrategy = ClusterResolutionStrategy.GOVT_PROXIMITY_ANCHOR,
    ):
        self.df = telemetry_df.copy()
        self.schools_df = schools_df
        self.geofence_radius_m = geofence_radius_m
        self.strategy = strategy

        if "giga_id_school" in self.df.columns:
            self.df = self.df.rename(columns={"giga_id_school": "school_id_giga"})
        if "device_hardware_id" in self.df.columns:
            self.df = self.df.rename(columns={"device_hardware_id": "device_id"})

        # Strict No-IP Fallback: Filter out null coordinates
        self.valid_geo_df = self.df[
            self.df["detected_latitude"].notna() & self.df["detected_longitude"].notna()
        ].copy()

        self.spatial_profiler = SpatialProfiler(self.valid_geo_df)
        self.facility_summary = self.spatial_profiler.build_facility_spatial_summary(
            schools_df=schools_df, strategy=strategy
        )
        self.mobility_analyzer = MobilityAnalyzer(
            telemetry_df=self.valid_geo_df,
            schools_df=schools_df,
            geofence_radius_m=geofence_radius_m,
            strategy=strategy,
        )

    def evaluate_facility_location_confidence(
        self, school_id_giga: str
    ) -> Dict[str, Any]:
        """
        Computes the 5-Factor Composite Location Confidence Score (0-100)
        with BSSID Coherence Penalty (P_coherence) and Flag Classification.
        """
        facility_records = self.valid_geo_df[
            self.valid_geo_df["school_id_giga"] == school_id_giga
        ].copy()

        if len(facility_records) < 5:
            return {
                "school_id_giga": school_id_giga,
                "confidence_score": 0.0,
                "validation_flag": "INSUFFICIENT_DATA",
                "reason": "Fewer than 5 valid spatial scans recorded in telemetry window.",
                "total_scans": len(facility_records),
            }

        # Operational Hours Filter (08:00 - 19:59 local device time)
        if "is_operational_hours" in facility_records.columns:
            op_records = facility_records[
                facility_records["is_operational_hours"]
            ].copy()
            if not op_records.empty:
                facility_records = op_records

        device_ids = facility_records["device_id"].unique()
        device_mobility_classes = []
        primary_centroids = []

        for dev_id in device_ids:
            dev_analysis = self.mobility_analyzer.analyze_device_mobility(dev_id)
            if "error" not in dev_analysis:
                device_mobility_classes.append(dev_analysis["mobility_class"])
                dev_df = dev_analysis["processed_df"]
                cluster_0 = dev_df[dev_df["cluster_id"] == 0]
                if not cluster_0.empty:
                    primary_centroids.append(
                        (
                            cluster_0["detected_latitude"].mean(),
                            cluster_0["detected_longitude"].mean(),
                        )
                    )

        # Get empirical centroid from facility summary
        fac_sum = self.facility_summary[
            self.facility_summary["school_id_giga"] == school_id_giga
        ]
        empirical_lat = fac_sum["empirical_centroid_lat"].iloc[0]
        empirical_lon = fac_sum["empirical_centroid_lon"].iloc[0]
        govt_lat = (
            fac_sum["govt_latitude"].iloc[0]
            if not fac_sum.empty and "govt_latitude" in fac_sum.columns
            else np.nan
        )
        govt_lon = (
            fac_sum["govt_longitude"].iloc[0]
            if not fac_sum.empty and "govt_longitude" in fac_sum.columns
            else np.nan
        )

        # Factor 1: Device Stability Profile (Max 30 pts)
        score_stability = (
            30.0
            if "STATIONARY" in device_mobility_classes
            else (20.0 if "COMMUTER" in device_mobility_classes else 10.0)
        )

        # Factor 2: Multi-Device Spatial Consensus (Max 25 pts)
        if len(primary_centroids) > 1:
            cent_arr = np.array(primary_centroids)
            dists = [
                haversine_distance_meters(
                    cent_arr[i][0], cent_arr[i][1], cent_arr[j][0], cent_arr[j][1]
                )
                for i in range(len(cent_arr))
                for j in range(i + 1, len(cent_arr))
            ]
            max_d = max(dists) if dists else 0.0
            score_consensus = (
                25.0
                if max_d <= 30.0
                else (25.0 * (1.0 - (max_d - 30.0) / 170.0) if max_d <= 200.0 else 0.0)
            )
        else:
            score_consensus = 12.5

        # Factor 3: BSSID Persistence (Max 20 pts)
        bssid_col = (
            "detected_wifi_bssid"
            if "detected_wifi_bssid" in facility_records.columns
            else "detected_bssid"
        )
        valid_bssids = facility_records[facility_records[bssid_col].notna()]
        score_bssid = (
            20.0
            if (not valid_bssids.empty and valid_bssids["local_date"].nunique() >= 3)
            else 10.0
        )

        # Factor 4: Data Temporal Depth (Max 15 pts)
        days_count = (
            facility_records["local_date"].nunique()
            if "local_date" in facility_records.columns
            else 1
        )
        score_depth = min(15.0, 15.0 * (days_count / 10.0))

        # Factor 5: API Precision Radius (Max 10 pts)
        accuracies = (
            facility_records["detected_location_accuracy"].values
            if "detected_location_accuracy" in facility_records.columns
            else np.ones(len(facility_records)) * 20.0
        )
        mean_acc = float(np.mean(accuracies))
        score_precision = max(0.0, 10.0 * (1.0 - (mean_acc - 10.0) / 90.0))

        raw_score = (
            score_stability
            + score_consensus
            + score_bssid
            + score_depth
            + score_precision
        )

        # BSSID Coherence Penalty (P_coherence) for BSSID splits > 2km
        max_bssid_dist_m = (
            fac_sum["max_bssid_dist_m"].iloc[0] if not fac_sum.empty else 0.0
        )
        if max_bssid_dist_m <= 1000.0:
            p_coherence = 1.0
        elif max_bssid_dist_m <= 2000.0:
            p_coherence = 1.0 - 0.5 * ((max_bssid_dist_m - 1000.0) / 1000.0)
        else:
            p_coherence = 0.1  # Severe penalty for > 2km split

        final_confidence_score = round(raw_score * p_coherence, 1)

        # Government Displacement & Flag Taxonomy
        govt_disp_m = haversine_distance_meters(
            empirical_lat, empirical_lon, govt_lat, govt_lon
        )
        hotspot_scan_pct = (
            fac_sum["hotspot_scan_pct"].iloc[0] if not fac_sum.empty else 0.0
        )

        if max_bssid_dist_m > 2000.0:
            validation_flag = "BSSID_SPATIAL_SPLIT"
        elif hotspot_scan_pct >= 50.0:
            validation_flag = "HOTSPOT_TETHERED_FACILITY"
        elif pd.isna(govt_disp_m):
            validation_flag = "NO_GOVT_PIN_AVAILABLE"
        elif final_confidence_score >= 70.0 and govt_disp_m <= 200.0:
            validation_flag = "VERIFIED_ACCURATE"
        elif final_confidence_score >= 70.0 and govt_disp_m > 500.0:
            validation_flag = "GOVT_PIN_MISMATCH"
        elif final_confidence_score >= 60.0 and 200.0 < govt_disp_m <= 500.0:
            validation_flag = "CAMPUS_DISPERSION"
        elif final_confidence_score < 50.0:
            validation_flag = "UNSTABLE_MOBILE_ONLY"
        else:
            validation_flag = "MINOR_DISCREPANCY"

        return {
            "school_id_giga": school_id_giga,
            "school_name": (
                fac_sum["school_name"].iloc[0]
                if not fac_sum.empty and "school_name" in fac_sum.columns
                else school_id_giga
            ),
            "confidence_score": final_confidence_score,
            "raw_score": round(raw_score, 1),
            "p_coherence": round(p_coherence, 2),
            "validation_flag": validation_flag,
            "govt_displacement_m": (
                round(govt_disp_m, 1) if pd.notna(govt_disp_m) else np.nan
            ),
            "max_bssid_dist_m": max_bssid_dist_m,
            "hotspot_scan_pct": hotspot_scan_pct,
            "empirical_latitude": round(empirical_lat, 6),
            "empirical_longitude": round(empirical_lon, 6),
            "govt_latitude": round(govt_lat, 6) if pd.notna(govt_lat) else np.nan,
            "govt_longitude": round(govt_lon, 6) if pd.notna(govt_lon) else np.nan,
            "total_scans": len(facility_records),
            "distinct_devices": len(device_ids),
            "mean_accuracy_m": round(mean_acc, 1),
        }

    def run_national_facility_audit(self) -> pd.DataFrame:
        """Runs the validation engine across all facilities."""
        results = [
            self.evaluate_facility_location_confidence(s)
            for s in self.valid_geo_df["school_id_giga"].unique()
        ]
        return (
            pd.DataFrame(results)
            .sort_values(by="confidence_score", ascending=False)
            .reset_index(drop=True)
        )

    def plot_facility_verification_dashboard(self, school_id_giga: str) -> go.Figure:
        """Dual-panel Plotly Executive Verification Dashboard."""
        eval_res = self.evaluate_facility_location_confidence(school_id_giga)

        fig = make_subplots(
            rows=1,
            cols=2,
            column_widths=[0.65, 0.35],
            specs=[[{"type": "mapbox"}, {"type": "xy"}]],
            subplot_titles=(
                f"Spatial Verification Map — {eval_res['school_name']}",
                f"Confidence Score ({eval_res['confidence_score']}/100)",
            ),
        )

        # Map Trace: Empirical Centroid (Green)
        fig.add_trace(
            go.Scattermapbox(
                lat=[eval_res["empirical_latitude"]],
                lon=[eval_res["empirical_longitude"]],
                mode="markers+text",
                marker=dict(size=18, color="#2ca02c", symbol="hospital"),
                text=["Empirical Centroid"],
                textposition="top center",
                name="Empirical Centroid",
            ),
            row=1,
            col=1,
        )

        # Map Trace: Govt Pin (Red)
        if pd.notna(eval_res["govt_latitude"]):
            fig.add_trace(
                go.Scattermapbox(
                    lat=[eval_res["govt_latitude"]],
                    lon=[eval_res["govt_longitude"]],
                    mode="markers+text",
                    marker=dict(size=18, color="#d62728", symbol="marker"),
                    text=[f"Govt Pin ({eval_res['govt_displacement_m']}m)"],
                    textposition="bottom center",
                    name="Government Pin",
                ),
                row=1,
                col=1,
            )

        # Bar Chart Trace
        categories = ["Raw Score", "Coherence Penalty", "Final Score"]
        vals = [
            eval_res["raw_score"],
            eval_res["p_coherence"] * 100.0,
            eval_res["confidence_score"],
        ]
        fig.add_trace(
            go.Bar(
                y=categories,
                x=vals,
                orientation="h",
                marker=dict(color=["#1f77b4", "#ff7f0e", "#2ca02c"]),
                text=[
                    f"{eval_res['raw_score']}/100",
                    f"x{eval_res['p_coherence']}",
                    f"{eval_res['confidence_score']}/100",
                ],
                textposition="auto",
                name="Score Components",
            ),
            row=1,
            col=2,
        )

        fig.update_layout(
            mapbox=dict(
                style="open-street-map",
                center=dict(
                    lat=eval_res["empirical_latitude"],
                    lon=eval_res["empirical_longitude"],
                ),
                zoom=14,
            ),
            title_text=f"GigaMeter Facility Audit — Flag: [{eval_res['validation_flag']}]",
            height=550,
            margin=dict(l=20, r=20, t=60, b=20),
        )
        return fig
