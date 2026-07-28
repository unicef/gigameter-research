"""
Module: src/facility_validator.py
Purpose: Consolidated Facility Location Truth Engine, Composite Confidence Scoring (0-100),
         Government Administrative Data Validation, and Executive Visualizations.
Rules: Aligned with GigaMeter Data Dictionary v2.2 (08:00 - 19:59 Operational Window).
"""

import numpy as np
import pandas as pd
from typing import Optional, Dict, Any, List
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from src.spatial_profiler import SpatialProfiler, haversine_distance_meters
from src.mobility_analyzer import MobilityAnalyzer


class FacilityValidator:
    """
    Facility Location Truth & Validation Engine for GigaMeter Telemetry.
    Consolidates multi-device spatial clusters into an empirical facility location,
    evaluates a 5-factor location confidence score (0-100), and classifies
    displacement against government administrative records.
    """

    def __init__(
        self,
        telemetry_df: pd.DataFrame,
        schools_df: Optional[pd.DataFrame] = None,
        geofence_radius_m: float = 200.0,
    ):
        self.df = telemetry_df.copy()
        self.schools_df = schools_df
        self.geofence_radius_m = geofence_radius_m

        # Standardize primary identifiers
        if "giga_id_school" in self.df.columns:
            self.df = self.df.rename(columns={"giga_id_school": "school_id_giga"})
        if "device_hardware_id" in self.df.columns:
            self.df = self.df.rename(columns={"device_hardware_id": "device_id"})

        # Enforce strict No-IP fallback policy: discard null coordinates
        self.valid_geo_df = self.df[
            self.df["detected_latitude"].notna() & self.df["detected_longitude"].notna()
        ].copy()

        # Initialize underlying profilers and analyzers
        self.spatial_profiler = SpatialProfiler(self.valid_geo_df)
        self.facility_summary = self.spatial_profiler.build_facility_spatial_summary(
            schools_df=schools_df
        )
        self.mobility_analyzer = MobilityAnalyzer(
            telemetry_df=self.valid_geo_df,
            schools_df=schools_df,
            geofence_radius_m=geofence_radius_m,
        )

    def evaluate_facility_location_confidence(
        self, school_id_giga: str
    ) -> Dict[str, Any]:
        """
        Computes the 5-Factor Composite Facility Location Confidence Score (0-100)
        and evaluates displacement against government administrative coordinates.
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

        # -------------------------------------------------------------------
        # LAYER 1: Disambiguation & Primary Cluster Isolation
        # -------------------------------------------------------------------
        # Filter strictly for active operational hours (08:00 - 19:59 local time)
        if "is_operational_hours" in facility_records.columns:
            op_records = facility_records[
                facility_records["is_operational_hours"]
            ].copy()
            if not op_records.empty:
                facility_records = op_records

        # Evaluate device mobility profiles registered to this school
        device_ids = facility_records["device_id"].unique()
        device_mobility_classes = []
        primary_centroids = []

        for dev_id in device_ids:
            dev_analysis = self.mobility_analyzer.analyze_device_mobility(dev_id)
            if "error" not in dev_analysis:
                device_mobility_classes.append(dev_analysis["mobility_class"])
                dev_df = dev_analysis["processed_df"]
                # Isolate Cluster 0 (Primary) for Stationary & Commuter devices
                cluster_0 = dev_df[dev_df["cluster_id"] == 0]
                if not cluster_0.empty:
                    primary_centroids.append(
                        (
                            cluster_0["detected_latitude"].mean(),
                            cluster_0["detected_longitude"].mean(),
                        )
                    )

        # -------------------------------------------------------------------
        # LAYER 2: Empirical Facility Centroid Calculation
        # -------------------------------------------------------------------
        lats = facility_records["detected_latitude"].values
        lons = facility_records["detected_longitude"].values
        accuracies = (
            facility_records["detected_location_accuracy"].values
            if "detected_location_accuracy" in facility_records.columns
            else np.ones(len(facility_records)) * 20.0
        )

        # Accuracy-Weighted Spatial Centroid: w_i = 1 / (accuracy_i^2)
        weights = 1.0 / np.square(np.maximum(accuracies, 1.0))
        empirical_lat = float(np.sum(lats * weights) / np.sum(weights))
        empirical_lon = float(np.sum(lons * weights) / np.sum(weights))

        # -------------------------------------------------------------------
        # LAYER 3: 5-Factor Location Confidence Score Engine (0 - 100)
        # -------------------------------------------------------------------
        # Factor 1: Device Stability Profile (Max 30 pts)
        if "STATIONARY" in device_mobility_classes:
            score_stability = 30.0
        elif "COMMUTER" in device_mobility_classes:
            score_stability = 20.0
        else:
            score_stability = 10.0

        # Factor 2: Multi-Device Spatial Consensus (Max 25 pts)
        if len(primary_centroids) > 1:
            cent_array = np.array(primary_centroids)
            dists = [
                haversine_distance_meters(
                    cent_array[i][0],
                    cent_array[i][1],
                    cent_array[j][0],
                    cent_array[j][1],
                )
                for i in range(len(cent_array))
                for j in range(i + 1, len(cent_array))
            ]
            max_d = max(dists) if dists else 0.0
            if max_d <= 30.0:
                score_consensus = 25.0
            elif max_d <= 200.0:
                score_consensus = 25.0 * (1.0 - (max_d - 30.0) / 170.0)
            else:
                score_consensus = 0.0
        else:
            score_consensus = 12.5  # Neutral baseline for single-device facilities

        # Factor 3: BSSID Persistence (Max 20 pts)
        bssid_col = (
            "detected_wifi_bssid"
            if "detected_wifi_bssid" in facility_records.columns
            else "detected_bssid"
        )
        valid_bssids = facility_records[facility_records[bssid_col].notna()]
        if not valid_bssids.empty:
            days_active = (
                valid_bssids["local_date"].nunique()
                if "local_date" in valid_bssids.columns
                else 1
            )
            score_bssid = 20.0 if days_active >= 3 else 10.0
        else:
            score_bssid = 10.0  # Derived from ambient background Wi-Fi scans

        # Factor 4: Data Temporal Depth (Max 15 pts)
        days_count = (
            facility_records["local_date"].nunique()
            if "local_date" in facility_records.columns
            else 1
        )
        score_depth = min(15.0, 15.0 * (days_count / 10.0))

        # Factor 5: API Precision Radius (Max 10 pts)
        mean_acc = float(np.mean(accuracies))
        score_precision = max(0.0, 10.0 * (1.0 - (mean_acc - 10.0) / 90.0))

        total_confidence_score = round(
            score_stability
            + score_consensus
            + score_bssid
            + score_depth
            + score_precision,
            1,
        )

        # -------------------------------------------------------------------
        # LAYER 4: Government Administrative Pin Validation & Flag Taxonomy
        # -------------------------------------------------------------------
        fac_sum = self.facility_summary[
            self.facility_summary["school_id_giga"] == school_id_giga
        ]
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

        govt_disp_m = haversine_distance_meters(
            empirical_lat, empirical_lon, govt_lat, govt_lon
        )

        # Determine Flag Taxonomy
        if pd.isna(govt_disp_m):
            validation_flag = "NO_GOVT_PIN_AVAILABLE"
        elif total_confidence_score >= 70.0 and govt_disp_m <= 200.0:
            validation_flag = "VERIFIED_ACCURATE"
        elif total_confidence_score >= 70.0 and govt_disp_m > 500.0:
            validation_flag = "GOVT_PIN_MISMATCH"
        elif total_confidence_score >= 60.0 and 200.0 < govt_disp_m <= 500.0:
            validation_flag = "CAMPUS_DISPERSION"
        elif total_confidence_score < 50.0:
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
            "confidence_score": total_confidence_score,
            "validation_flag": validation_flag,
            "govt_displacement_m": (
                round(govt_disp_m, 1) if pd.notna(govt_disp_m) else np.nan
            ),
            "empirical_latitude": round(empirical_lat, 6),
            "empirical_longitude": round(empirical_lon, 6),
            "govt_latitude": round(govt_lat, 6) if pd.notna(govt_lat) else np.nan,
            "govt_longitude": round(govt_lon, 6) if pd.notna(govt_lon) else np.nan,
            "total_scans": len(facility_records),
            "distinct_devices": len(device_ids),
            "mean_accuracy_m": round(mean_acc, 1),
            "score_breakdown": {
                "stability": round(score_stability, 1),
                "consensus": round(score_consensus, 1),
                "bssid": round(score_bssid, 1),
                "depth": round(score_depth, 1),
                "precision": round(score_precision, 1),
            },
        }

    def run_national_facility_audit(self) -> pd.DataFrame:
        """Runs the validation engine across all facilities in the dataset."""
        results = []
        for school_id in self.valid_geo_df["school_id_giga"].unique():
            res = self.evaluate_facility_location_confidence(school_id)
            # Flatten score_breakdown dictionary for DataFrame export
            if "score_breakdown" in res:
                breakdown = res.pop("score_breakdown")
                for k, v in breakdown.items():
                    res[f"score_{k}"] = v
            results.append(res)

        audit_df = pd.DataFrame(results)
        return audit_df.sort_values(by="confidence_score", ascending=False).reset_index(
            drop=True
        )

    # -------------------------------------------------------------------
    # PLOTLY EXECUTIVE DASHBOARD
    # -------------------------------------------------------------------
    def plot_facility_verification_dashboard(self, school_id_giga: str) -> go.Figure:
        """
        Generates a dual-panel Plotly Executive Dashboard:
        - Left Panel: Mapbox Satellite Map overlaying Government Pin vs Empirical Centroid.
        - Right Panel: Horizontal Bar Chart breaking down the 5 Score Components.
        """
        eval_res = self.evaluate_facility_location_confidence(school_id_giga)
        if (
            eval_res["confidence_score"] == 0.0
            and eval_res["validation_flag"] == "INSUFFICIENT_DATA"
        ):
            raise ValueError(
                f"Insufficient telemetry data to build dashboard for {school_id_giga}"
            )

        # Create 1x2 Subplots (Map on left, Bar Chart on right)
        fig = make_subplots(
            rows=1,
            cols=2,
            column_widths=[0.65, 0.35],
            specs=[[{"type": "mapbox"}, {"type": "xy"}]],
            subplot_titles=(
                f"Spatial Verification Map — {eval_res['school_name']}",
                f"Confidence Score Breakdown ({eval_res['confidence_score']}/100)",
            ),
        )

        # 1. Map Traces
        # Empirical Centroid (Green)
        fig.add_trace(
            go.Scattermapbox(
                lat=[eval_res["empirical_latitude"]],
                lon=[eval_res["empirical_longitude"]],
                mode="markers+text",
                marker=dict(size=18, color="#2ca02c", symbol="hospital"),
                text=["Empirical Facility Centroid"],
                textposition="top center",
                name="Empirical Centroid",
            ),
            row=1,
            col=1,
        )

        # Official Government Pin (Red)
        if pd.notna(eval_res["govt_latitude"]):
            fig.add_trace(
                go.Scattermapbox(
                    lat=[eval_res["govt_latitude"]],
                    lon=[eval_res["govt_longitude"]],
                    mode="markers+text",
                    marker=dict(size=18, color="#d62728", symbol="marker"),
                    text=[f"Govt Pin (Disp: {eval_res['govt_displacement_m']}m)"],
                    textposition="bottom center",
                    name="Government Pin",
                ),
                row=1,
                col=1,
            )

        # 2. Score Breakdown Bar Chart
        breakdown = eval_res["score_breakdown"]
        categories = [
            "Stability",
            "Consensus",
            "BSSID Depth",
            "Temporal Depth",
            "API Precision",
        ]
        scores = [
            breakdown["stability"],
            breakdown["consensus"],
            breakdown["bssid"],
            breakdown["depth"],
            breakdown["precision"],
        ]
        max_scores = [30, 25, 20, 15, 10]

        fig.add_trace(
            go.Bar(
                y=categories,
                x=scores,
                orientation="h",
                marker=dict(color="#1f77b4"),
                text=[f"{s}/{m}" for s, m in zip(scores, max_scores)],
                textposition="auto",
                name="Component Score",
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
            title_text=f"GigaMeter Facility Location Audit — Flag: [{eval_res['validation_flag']}]",
            height=550,
            margin=dict(l=20, r=20, t=60, b=20),
            showlegend=True,
        )

        return fig
