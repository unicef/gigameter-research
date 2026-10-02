"""
Module: src/facility_validator.py
Purpose: Two-Track Facility Location Truth Engine, Hardware Integrity Scoring,
         BSSID Coherence Penalty, Government Data Validation, Caching, and Plotly Visualisations.
Rules: Aligned with GigaMeter Data Dictionary v2.2 (08:00 - 19:59 Operational Window).
"""

import numpy as np
import pandas as pd
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Union
import plotly.express as px
import plotly.graph_objects as go

from .spatial_profiler import (
    SpatialProfiler,
    haversine_distance_meters,
    ClusterResolutionStrategy,
)
from .mobility_analyzer import MobilityAnalyzer
from src.utils.data_loader import TelemetryLoader


class FacilityValidator:
    """
    Two-Track Facility Location Truth & Validation Engine for GigaMeter Telemetry.

    Track 1: Location Truth (Pillar 3)
             Evaluates building location against official government records using
             the unpenalized spatial confidence of the primary cluster.

    Track 2: Hardware Integrity (Pillars 1 & 2)
             Evaluates device reliability, detects mobile hotspots and spatial splits (> 2km),
             and applies the multiplicative BSSID Coherence Penalty (P_coherence).
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
        geofence_radius_m: float = 200.0,
        strategy: ClusterResolutionStrategy = ClusterResolutionStrategy.GOVT_PROXIMITY_ANCHOR,
    ) -> None:
        """
        Load canonical telemetry and build the two-track facility audit.

        Provide exactly one of `telemetry_df`, `file_path`, or `query_name`.
        The spatial summary is built once and passed into the mobility engine.

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
            geofence_radius_m: Campus radius around the empirical centroid.
            strategy: Primary cluster selection mode for BSSID splits.
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
        self.geofence_radius_m = geofence_radius_m
        self.strategy = strategy

        # In-Memory Cache for National Audit Results
        self._national_audit_cache: Optional[pd.DataFrame] = None

        # Strict No-IP Fallback: Filter out null coordinates
        self.valid_geo_df = self.df[
            self.df["detected_latitude"].notna() & self.df["detected_longitude"].notna()
        ].copy()

        self.spatial_profiler = SpatialProfiler(self.valid_geo_df)
        self.facility_summary = self.spatial_profiler.build_facility_spatial_summary(
            strategy=strategy
        )
        self.mobility_analyzer = MobilityAnalyzer(
            telemetry_df=self.valid_geo_df,
            geofence_radius_m=geofence_radius_m,
            strategy=strategy,
            facility_summary=self.facility_summary,
        )

    def evaluate_facility_location_confidence(
        self, school_id_giga: str
    ) -> Dict[str, Any]:
        """
        Computes the Two-Track Validation Engine metrics for a given facility:
        - Track 1: Location Truth (location_confidence_score, location_verification_flag)
        - Track 2: Hardware Health (hardware_health_score, hardware_anomaly_tags)
        - Mobility Counts: Detailed counts of distinct devices in each mobility class.
        """
        facility_records = self.valid_geo_df[
            self.valid_geo_df["school_id_giga"] == school_id_giga
        ].copy()

        if len(facility_records) < 5:
            return {
                "school_id_giga": school_id_giga,
                "school_name": school_id_giga,
                "location_confidence_score": 0.0,
                "location_verification_flag": "INSUFFICIENT_DATA",
                "hardware_health_score": 0.0,
                "hardware_anomaly_tags": [],
                "reason": "Fewer than 5 valid spatial scans recorded in telemetry window.",
                "total_scans": len(facility_records),
                "distinct_devices": 0,
                "stationary_devices_count": 0,
                "commuter_devices_count": 0,
                "relocated_devices_count": 0,
                "high_mobility_devices_count": 0,
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

        # -------------------------------------------------------------------
        # Mobility Breakdown Counts per Facility
        # -------------------------------------------------------------------
        stationary_count = device_mobility_classes.count("STATIONARY")
        commuter_count = device_mobility_classes.count("COMMUTER")
        relocated_count = device_mobility_classes.count("RELOCATED")
        high_mobility_count = device_mobility_classes.count("HIGH_MOBILITY")

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

        # -------------------------------------------------------------------
        # 5-Factor Raw Confidence Calculation (Unpenalized Cluster Score)
        # -------------------------------------------------------------------
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
        if "detected_wifi_bssid" in facility_records.columns:
            valid_bssids = facility_records[
                facility_records["detected_wifi_bssid"].notna()
            ]
        else:
            valid_bssids = facility_records.iloc[0:0]
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

        # -------------------------------------------------------------------
        # TRACK 1: Location Truth (Pillar 3)
        # Evaluates the dominant cluster against Government Records
        # -------------------------------------------------------------------
        location_confidence_score = round(raw_score, 1)
        govt_disp_m = haversine_distance_meters(
            empirical_lat, empirical_lon, govt_lat, govt_lon
        )

        if pd.isna(govt_disp_m):
            location_verification_flag = "NO_GOVT_PIN_AVAILABLE"
        elif location_confidence_score >= 70.0 and govt_disp_m <= 200.0:
            location_verification_flag = "VERIFIED_ACCURATE"
        elif location_confidence_score >= 70.0 and govt_disp_m > 500.0:
            location_verification_flag = "GOVT_PIN_MISMATCH"
        elif location_confidence_score >= 60.0 and 200.0 < govt_disp_m <= 500.0:
            location_verification_flag = "CAMPUS_DISPERSION"
        elif location_confidence_score < 50.0:
            location_verification_flag = "UNSTABLE_MOBILE_ONLY"
        else:
            location_verification_flag = "MINOR_DISCREPANCY"

        # -------------------------------------------------------------------
        # TRACK 2: Hardware Integrity (Pillars 1 & 2)
        # Evaluates device reliability, mobile hotspots, and BSSID splits (> 2km)
        # -------------------------------------------------------------------
        max_bssid_dist_m = (
            fac_sum["max_bssid_dist_m"].iloc[0] if not fac_sum.empty else 0.0
        )
        hotspot_scan_pct = (
            fac_sum["hotspot_scan_pct"].iloc[0] if not fac_sum.empty else 0.0
        )

        # Compute BSSID Coherence Penalty (P_coherence)
        if max_bssid_dist_m <= 1000.0:
            p_coherence = 1.0
        elif max_bssid_dist_m <= 2000.0:
            p_coherence = 1.0 - 0.5 * ((max_bssid_dist_m - 1000.0) / 1000.0)
        else:
            p_coherence = 0.1  # Severe penalty for > 2km spatial split

        hardware_health_score = round(raw_score * p_coherence, 1)

        # Generate Decoupled Hardware Anomaly Tags
        hardware_anomaly_tags = []
        if max_bssid_dist_m > 2000.0:
            hardware_anomaly_tags.append("BSSID_SPATIAL_SPLIT")
        if hotspot_scan_pct >= 50.0:
            hardware_anomaly_tags.append("HOTSPOT_TETHERED_FACILITY")

        return {
            "school_id_giga": school_id_giga,
            "school_name": (
                fac_sum["school_name"].iloc[0]
                if not fac_sum.empty and "school_name" in fac_sum.columns
                else school_id_giga
            ),
            # Track 1: Location Truth Metrics
            "location_confidence_score": location_confidence_score,
            "location_verification_flag": location_verification_flag,
            "govt_displacement_m": (
                round(govt_disp_m, 1) if pd.notna(govt_disp_m) else np.nan
            ),
            "empirical_latitude": round(empirical_lat, 6),
            "empirical_longitude": round(empirical_lon, 6),
            "govt_latitude": round(govt_lat, 6) if pd.notna(govt_lat) else np.nan,
            "govt_longitude": round(govt_lon, 6) if pd.notna(govt_lon) else np.nan,
            # Track 2: Hardware Health & Anomaly Metrics
            "hardware_health_score": hardware_health_score,
            "hardware_anomaly_tags": hardware_anomaly_tags,
            "p_coherence": round(p_coherence, 2),
            "max_bssid_dist_m": max_bssid_dist_m,
            "hotspot_scan_pct": hotspot_scan_pct,
            # Mobility Device Breakdown Counts
            "distinct_devices": len(device_ids),
            "stationary_devices_count": stationary_count,
            "commuter_devices_count": commuter_count,
            "relocated_devices_count": relocated_count,
            "high_mobility_devices_count": high_mobility_count,
            "device_mobility_counts": {
                "stationary": stationary_count,
                "commuter": commuter_count,
                "relocated": relocated_count,
                "high_mobility": high_mobility_count,
            },
            # Diagnostic Metadata
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

    def run_national_facility_audit(self, force_refresh: bool = False) -> pd.DataFrame:
        """
        Runs the Two-Track validation engine across all facilities in the dataset.
        Results are cached in `self._national_audit_cache` to avoid redundant multi-pass calculations.
        Set `force_refresh=True` to clear and re-execute the audit.
        """
        if self._national_audit_cache is not None and not force_refresh:
            return self._national_audit_cache

        results = []
        for school_id in self.valid_geo_df["school_id_giga"].unique():
            res = self.evaluate_facility_location_confidence(school_id)
            if "score_breakdown" in res:
                breakdown = res.pop("score_breakdown")
                for k, v in breakdown.items():
                    res[f"score_{k}"] = v

            # Unnest mobility count dict if present
            if "device_mobility_counts" in res:
                res.pop("device_mobility_counts")

            res["hardware_anomaly_tags"] = (
                ", ".join(res["hardware_anomaly_tags"])
                if res["hardware_anomaly_tags"]
                else "NONE"
            )
            results.append(res)

        audit_df = pd.DataFrame(results)
        if not audit_df.empty:
            audit_df = audit_df.sort_values(
                by="location_confidence_score", ascending=False
            ).reset_index(drop=True)

        self._national_audit_cache = audit_df
        return self._national_audit_cache

    def summarize_national_audit(self) -> Dict[str, Any]:
        """
        Summarize the cached national audit for the executive metric cards.

        Uses `run_national_facility_audit()` so a second call does not rebuild
        the audit. An empty audit returns zeros. Stationary facilities are
        those with `score_stability == 30.0`. Percentages and the mean
        hardware score are rounded to one decimal.

        Returns:
            Facility counts by location flag, stationary-hardware share,
            anomaly-tag counts, and the mean hardware health score.
        """
        audit_df = self.run_national_facility_audit()
        empty = {
            "total_facilities": 0,
            "verified_accurate": 0,
            "govt_pin_mismatch": 0,
            "campus_dispersion": 0,
            "stationary_facilities": 0,
            "stationary_pct": 0.0,
            "bssid_spatial_splits": 0,
            "hotspot_tethered_facilities": 0,
            "mean_hardware_health_score": 0.0,
        }
        if audit_df.empty:
            return empty

        total_facilities = len(audit_df)
        if "score_stability" in audit_df.columns:
            stationary_facilities = int((audit_df["score_stability"] == 30.0).sum())
        else:
            stationary_facilities = 0
        flags = audit_df["location_verification_flag"]
        tags = audit_df["hardware_anomaly_tags"]
        return {
            "total_facilities": total_facilities,
            "verified_accurate": int((flags == "VERIFIED_ACCURATE").sum()),
            "govt_pin_mismatch": int((flags == "GOVT_PIN_MISMATCH").sum()),
            "campus_dispersion": int((flags == "CAMPUS_DISPERSION").sum()),
            "stationary_facilities": stationary_facilities,
            "stationary_pct": round(
                (stationary_facilities / total_facilities) * 100.0, 1
            ),
            "bssid_spatial_splits": int(
                tags.str.contains("BSSID_SPATIAL_SPLIT", na=False).sum()
            ),
            "hotspot_tethered_facilities": int(
                tags.str.contains("HOTSPOT_TETHERED_FACILITY", na=False).sum()
            ),
            "mean_hardware_health_score": round(
                float(audit_df["hardware_health_score"].mean()), 1
            ),
        }

    def plot_stationary_facility_percentage(self) -> go.Figure:
        """
        Calculates and plots the percentage of national facilities that have at least
        one STATIONARY monitoring device (`score_stability == 30.0`).
        Uses the cached national audit DataFrame for fast Streamlit rendering.
        """
        summary = self.summarize_national_audit()
        if summary["total_facilities"] == 0:
            raise ValueError(
                "No valid facilities available for national mobility analysis."
            )

        total_facilities = summary["total_facilities"]
        has_stationary = summary["stationary_facilities"]
        no_stationary = total_facilities - has_stationary
        pct_stationary = summary["stationary_pct"]

        labels = ["Anchored by Stationary Device", "Mobile / Commuter Only"]
        values = [has_stationary, no_stationary]
        colors = ["#2ca02c", "#ff7f0e"]

        fig = go.Figure(
            data=[
                go.Pie(
                    labels=labels,
                    values=values,
                    hole=0.5,
                    marker=dict(colors=colors),
                    textinfo="label+percent",
                    hoverinfo="label+value+percent",
                    hovertemplate=(
                        "<b>%{label}</b><br>"
                        "Facilities: %{value}<br>"
                        "Share: %{percent}<extra></extra>"
                    ),
                )
            ]
        )

        fig.update_layout(
            title=dict(
                text=(
                    f"National Stationary Device Coverage<br>"
                    f"<sup><b>{pct_stationary}%</b> ({has_stationary}/{total_facilities}) Facilities "
                    f"Monitored by Fixed Hardware</sup>"
                ),
                x=0.01,
                y=0.95,
                font=dict(size=16),
            ),
            height=380,
            margin=dict(l=20, r=20, t=70, b=20),
            template="plotly_white",
            showlegend=True,
            legend=dict(
                orientation="h", yanchor="bottom", y=-0.1, xanchor="center", x=0.5
            ),
        )

        return fig

    def plot_track_comparison(self, school_id_giga: str) -> go.Figure:
        """
        Standalone Plotly Figure designed for Streamlit UI containers.
        Renders a side-by-side comparison bar chart contrasting Track 1 (Location Truth)
        and Track 2 (Hardware Health), overlaid with anomaly tag annotations.
        """
        eval_res = self.evaluate_facility_location_confidence(school_id_giga)

        loc_score = eval_res["location_confidence_score"]
        hw_score = eval_res["hardware_health_score"]
        loc_flag = eval_res["location_verification_flag"]
        anomaly_tags = eval_res["hardware_anomaly_tags"]
        tags_str = ", ".join(anomaly_tags) if anomaly_tags else "NONE"

        categories = [
            "Track 1: Location Truth<br>(Pillar 3 Building Verification)",
            "Track 2: Hardware Health<br>(Pillar 1 & 2 Device Reliability)",
        ]
        scores = [loc_score, hw_score]

        # Color palette based on threshold health
        loc_color = (
            "#2ca02c"
            if loc_score >= 70
            else ("#ff7f0e" if loc_score >= 50 else "#d62728")
        )
        hw_color = (
            "#1f77b4"
            if hw_score >= 70
            else ("#ff7f0e" if hw_score >= 50 else "#d62728")
        )

        fig = go.Figure()

        fig.add_trace(
            go.Bar(
                y=categories,
                x=scores,
                orientation="h",
                marker=dict(color=[loc_color, hw_color]),
                text=[f"{loc_score:.1f} / 100", f"{hw_score:.1f} / 100"],
                textposition="auto",
                textfont=dict(size=14, color="white"),
                name="Two-Track Scores",
            )
        )

        fig.update_layout(
            title=dict(
                text=f"Two-Track Engine Audit - {eval_res['school_name']}<br><sup>Location Flag: <b>{loc_flag}</b> | Anomaly Tags: <b>{tags_str}</b></sup>",
                x=0.01,
                y=0.95,
                font=dict(size=16),
            ),
            xaxis=dict(title="Score (0 - 100)", range=[0, 105]),
            yaxis=dict(autorange="reversed"),
            height=320,
            margin=dict(l=10, r=20, t=70, b=40),
            template="plotly_white",
        )

        return fig

    def plot_facility_map(self, school_id_giga: str) -> go.Figure:
        """
        Standalone Mapbox Spatial Inspection Map.
        Overlays Empirical Centroid (Green), Government Pin (Red),
        and individual Telemetry Scans.
        """
        eval_res = self.evaluate_facility_location_confidence(school_id_giga)
        if (
            eval_res["location_confidence_score"] == 0.0
            and eval_res["location_verification_flag"] == "INSUFFICIENT_DATA"
        ):
            raise ValueError(
                f"Insufficient telemetry data for school: {school_id_giga}"
            )

        fig = go.Figure()

        # 1. Empirical Centroid (Green Marker)
        fig.add_trace(
            go.Scattermapbox(
                lat=[eval_res["empirical_latitude"]],
                lon=[eval_res["empirical_longitude"]],
                mode="markers+text",
                marker=dict(size=20, color="#2ca02c"),
                text=["Empirical Centroid"],
                textposition="top center",
                textfont=dict(color="black", size=12),
                name="Empirical Facility Centroid",
            )
        )

        # 2. Official Government Pin (Red Marker)
        if pd.notna(eval_res["govt_latitude"]):
            fig.add_trace(
                go.Scattermapbox(
                    lat=[eval_res["govt_latitude"]],
                    lon=[eval_res["govt_longitude"]],
                    mode="markers+text",
                    marker=dict(size=20, color="#d62728"),
                    text=[f"Govt Pin ({eval_res['govt_displacement_m']}m Mismatch)"],
                    textposition="bottom center",
                    textfont=dict(color="black", size=12),
                    name="Official Government Pin",
                )
            )

        # 3. Individual Telemetry Scans
        fac_scans = self.valid_geo_df[
            self.valid_geo_df["school_id_giga"] == school_id_giga
        ]
        if not fac_scans.empty:
            fig.add_trace(
                go.Scattermapbox(
                    lat=fac_scans["detected_latitude"],
                    lon=fac_scans["detected_longitude"],
                    mode="markers",
                    marker=dict(size=9, color="#1f77b4", opacity=0.6),
                    hoverinfo="text",
                    hovertext=fac_scans.apply(
                        lambda r: (
                            f"Device: {r.get('device_id', 'N/A')}<br>"
                            f"BSSID: {r.get('detected_wifi_bssid', 'Ambient Scan')}<br>"
                            f"Accuracy: {r.get('detected_location_accuracy', 0):.1f}m"
                        ),
                        axis=1,
                    ),
                    name="Individual Scans",
                )
            )

        tags_str = (
            eval_res["hardware_anomaly_tags"]
            if eval_res["hardware_anomaly_tags"]
            else "NONE"
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
            title=dict(
                text=f"Spatial Map: {eval_res['school_name']} [{eval_res['location_verification_flag']}] (Anomalies: {tags_str})",
                x=0.01,
                y=0.98,
            ),
            height=600,
            margin=dict(l=10, r=10, t=40, b=10),
            legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
        )
        return fig

    def plot_score_breakdown(self, school_id_giga: str) -> go.Figure:
        """
        Standalone Horizontal Bar Chart detailing the 5 confidence components
        and the multiplicative BSSID Coherence Penalty.
        """
        eval_res = self.evaluate_facility_location_confidence(school_id_giga)
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

        fig = go.Figure()

        # Component Scores
        fig.add_trace(
            go.Bar(
                y=categories,
                x=scores,
                orientation="h",
                marker=dict(color="#1f77b4"),
                text=[f"{s}/{m} pts" for s, m in zip(scores, max_scores)],
                textposition="auto",
                name="Score Components",
            )
        )

        fig.update_layout(
            title=dict(
                text=(
                    f"Confidence Breakdown - Location Score: {eval_res['location_confidence_score']}/100 | "
                    f"Hardware Health: {eval_res['hardware_health_score']}/100 (Coherence Penalty: x{eval_res['p_coherence']})"
                ),
                x=0.01,
                y=0.98,
            ),
            xaxis=dict(title="Points Assigned", range=[0, 35]),
            yaxis=dict(autorange="reversed"),
            height=350,
            margin=dict(l=10, r=10, t=40, b=30),
            template="plotly_white",
        )
        return fig

    def plot_two_track_actionability_matrix(self) -> go.Figure:
        """
        Renders an executive 4-quadrant scatter matrix:
        - X-Axis: Track 2 Hardware Health Score (0-100)
        - Y-Axis: Track 1 Location Confidence Score (0-100)
        """
        audit_df = self.run_national_facility_audit()
        if audit_df.empty:
            fig = go.Figure()
            fig.update_layout(title="No national audit data available")
            return fig

        fig = px.scatter(
            audit_df,
            x="hardware_health_score",
            y="location_confidence_score",
            color="location_verification_flag",
            hover_data=[
                "school_id_giga",
                "school_name",
                "govt_displacement_m",
                "hardware_anomaly_tags",
            ],
            labels={
                "hardware_health_score": "Track 2: Hardware Health Score (0-100)",
                "location_confidence_score": "Track 1: Location Confidence Score (0-100)",
                "location_verification_flag": "Location Flag",
            },
            title="Two-Track Actionability & Triage Matrix (Pillars 1, 2 & 3)",
        )

        # Quadrant Threshold Lines
        fig.add_vline(
            x=70.0,
            line_dash="dash",
            line_color="gray",
            annotation_text="Hardware Threshold (70)",
        )
        fig.add_hline(
            y=70.0,
            line_dash="dash",
            line_color="gray",
            annotation_text="Location Threshold (70)",
        )

        fig.update_layout(
            xaxis=dict(range=[0, 105]),
            yaxis=dict(range=[0, 105]),
            template="plotly_white",
            height=400,
            margin=dict(l=10, r=10, t=50, b=30),
            legend=dict(
                orientation="v",
                xanchor="right",
                yanchor="bottom",
                x=0.99,
                y=0.01,
                font=dict(size=8),
                title_text="",
            ),
        )
        return fig
