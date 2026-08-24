"""
Module: src/mobility_analyzer.py
Purpose: Pillar 1 Entity Geofencing, DBSCAN Spatial Mobility Clustering,
         Trajectory Classification, and Plotly Visualizations.
Rules: Aligned with GigaMeter Data Dictionary v2.2 (08:00 - 19:59 Operational Window).
"""

import numpy as np
import pandas as pd
from typing import Optional, Dict, Any
from sklearn.cluster import DBSCAN
import plotly.express as px
import plotly.graph_objects as go

from src.spatial_profiler import (
    SpatialProfiler,
    haversine_distance_meters,
    ClusterResolutionStrategy,
)


class MobilityAnalyzer:
    """
    Pillar 1 Mobility Engine for GigaMeter Telemetry.
    Performs device geofencing audits, DBSCAN spatial clustering,
    behavioral trajectory classification, and Plotly spatial mapping.
    """

    def __init__(
        self,
        telemetry_df: pd.DataFrame,
        schools_df: Optional[pd.DataFrame] = None,
        geofence_radius_m: float = 200.0,
        strategy: ClusterResolutionStrategy = ClusterResolutionStrategy.GOVT_PROXIMITY_ANCHOR,
    ):
        self.df = telemetry_df.copy()
        self.geofence_radius_m = geofence_radius_m

        if "giga_id_school" in self.df.columns:
            self.df = self.df.rename(columns={"giga_id_school": "school_id_giga"})
        if "device_hardware_id" in self.df.columns:
            self.df = self.df.rename(columns={"device_hardware_id": "device_id"})

        # Strict No-IP Fallback: Filter out missing coordinates
        self.valid_geo_df = self.df[
            self.df["detected_latitude"].notna() & self.df["detected_longitude"].notna()
        ].copy()

        # Build empirical facility centroids
        self.profiler = SpatialProfiler(self.valid_geo_df)
        self.facility_summary = self.profiler.build_facility_spatial_summary(
            schools_df=schools_df, strategy=strategy
        )

        centroid_map_lat = dict(
            zip(
                self.facility_summary["school_id_giga"],
                self.facility_summary["empirical_centroid_lat"],
            )
        )
        centroid_map_lon = dict(
            zip(
                self.facility_summary["school_id_giga"],
                self.facility_summary["empirical_centroid_lon"],
            )
        )

        self.valid_geo_df["facility_centroid_lat"] = self.valid_geo_df[
            "school_id_giga"
        ].map(centroid_map_lat)
        self.valid_geo_df["facility_centroid_lon"] = self.valid_geo_df[
            "school_id_giga"
        ].map(centroid_map_lon)

        self.valid_geo_df["displacement_m"] = self.valid_geo_df.apply(
            lambda r: haversine_distance_meters(
                r["detected_latitude"],
                r["detected_longitude"],
                r["facility_centroid_lat"],
                r["facility_centroid_lon"],
            ),
            axis=1,
        )
        self.valid_geo_df["is_within_geofence"] = (
            self.valid_geo_df["displacement_m"] <= self.geofence_radius_m
        )

    def analyze_device_mobility(
        self, device_id: str, cluster_eps_m: float = 150.0, min_samples: int = 3
    ) -> Dict[str, Any]:
        """
        Analyzes a single device's trajectory using DBSCAN clustering.
        Classifies behavior as: STATIONARY, COMMUTER, RELOCATED, or HIGH_MOBILITY.
        """
        device_data = self.valid_geo_df[
            self.valid_geo_df["device_id"] == device_id
        ].copy()

        if device_data.empty:
            return {
                "error": f"No valid geographic scans found for device_id: {device_id}"
            }

        school_id = device_data["school_id_giga"].iloc[0]
        school_name = (
            device_data["school_name"].iloc[0]
            if "school_name" in device_data.columns
            else school_id
        )

        timestamp_col = (
            "local_created_timestamp"
            if "local_created_timestamp" in device_data.columns
            else "created_timestamp"
        )
        device_data = device_data.sort_values(by=timestamp_col)

        # -------------------------------------------------------------------
        # Step 1: DBSCAN Spatial Clustering (Haversine Metric)
        # -------------------------------------------------------------------
        coords_rad = np.radians(
            device_data[["detected_latitude", "detected_longitude"]].values
        )
        kms_per_radian = 6371.0088
        eps_rad = (cluster_eps_m / 1000.0) / kms_per_radian

        db = DBSCAN(eps=eps_rad, min_samples=min_samples, metric="haversine").fit(
            coords_rad
        )
        device_data["cluster_id"] = db.labels_

        unique_clusters = set(db.labels_) - {-1}
        cluster_count = len(unique_clusters)
        total_scans = len(device_data)
        compliant_scans = int(device_data["is_within_geofence"].sum())
        compliance_rate_pct = round((compliant_scans / total_scans) * 100.0, 1)

        # -------------------------------------------------------------------
        # Step 2: Behavioral Classification Engine
        # -------------------------------------------------------------------
        if cluster_count <= 1 and compliance_rate_pct >= 90.0:
            mobility_class = "STATIONARY"
        elif cluster_count >= 2:
            device_data["date"] = pd.to_datetime(device_data[timestamp_col]).dt.date
            cluster_dates = (
                device_data[device_data["cluster_id"] != -1]
                .groupby("cluster_id")["date"]
                .agg(["min", "max"])
            )

            # Check sequential relocation
            cluster_ids = list(cluster_dates.index)
            is_sequential = False
            if len(cluster_ids) == 2:
                if (
                    cluster_dates.loc[cluster_ids[0], "max"]
                    < cluster_dates.loc[cluster_ids[1], "min"]
                ) or (
                    cluster_dates.loc[cluster_ids[1], "max"]
                    < cluster_dates.loc[cluster_ids[0], "min"]
                ):
                    is_sequential = True

            if is_sequential:
                mobility_class = "RELOCATED"
            else:
                if "is_operational_hours" in device_data.columns:
                    off_hour_scans = device_data[~device_data["is_operational_hours"]]
                    mobility_class = (
                        "COMMUTER"
                        if not off_hour_scans.empty
                        and (off_hour_scans["cluster_id"] != 0).any()
                        else "HIGH_MOBILITY"
                    )
                else:
                    mobility_class = "COMMUTER"
        else:
            mobility_class = "HIGH_MOBILITY"

        return {
            "device_id": device_id,
            "school_id_giga": school_id,
            "school_name": school_name,
            "total_scans": total_scans,
            "compliant_scans": compliant_scans,
            "compliance_rate_pct": compliance_rate_pct,
            "cluster_count": cluster_count,
            "mobility_class": mobility_class,
            "max_displacement_m": round(float(device_data["displacement_m"].max()), 1),
            "median_displacement_m": round(
                float(device_data["displacement_m"].median()), 1
            ),
            "processed_df": device_data,
        }

    def generate_facility_mobility_report(self) -> pd.DataFrame:
        """Generates a facility-wide mobility audit report for all devices."""
        results = []
        for device_id in self.valid_geo_df["device_id"].unique():
            metrics = self.analyze_device_mobility(device_id)
            if "error" not in metrics:
                results.append(
                    {k: v for k, v in metrics.items() if k != "processed_df"}
                )
        return (
            pd.DataFrame(results)
            .sort_values(by="compliance_rate_pct", ascending=True)
            .reset_index(drop=True)
        )

    def plot_device_mobility_map(self, device_id: str) -> go.Figure:
        """Map 1: Interactive Plotly Mapbox Spatial Cluster Map."""
        analysis = self.analyze_device_mobility(device_id)
        if "error" in analysis:
            raise ValueError(analysis["error"])

        df_dev = analysis["processed_df"].copy()
        school_lat, school_lon = (
            df_dev["facility_centroid_lat"].iloc[0],
            df_dev["facility_centroid_lon"].iloc[0],
        )
        df_dev["cluster_label"] = df_dev["cluster_id"].apply(
            lambda x: "Noise / Outlier" if x == -1 else f"Cluster {x}"
        )

        fig = px.scatter_mapbox(
            df_dev,
            lat="detected_latitude",
            lon="detected_longitude",
            color="cluster_label",
            size="detected_location_accuracy",
            size_max=15,
            hover_data=[
                "device_id",
                "displacement_m",
                "detected_location_accuracy",
                "is_operational_hours",
            ],
            title=f"Pillar 1 Spatial Mobility Audit — Device: {device_id} ({analysis['mobility_class']})",
            zoom=13,
            height=650,
        )
        fig.add_trace(
            go.Scattermapbox(
                lat=[school_lat],
                lon=[school_lon],
                mode="markers+text",
                marker=dict(size=18, color="red"),
                text=["Facility Anchor"],
                textposition="top center",
                name="Facility Anchor",
            )
        )
        fig.update_layout(
            mapbox_style="open-street-map", margin=dict(l=10, r=10, t=50, b=10)
        )
        return fig

    def plot_displacement_timeline(self, device_id: str) -> go.Figure:
        """Map 2: Distance-over-Time Plotly Displacement Timeline."""
        analysis = self.analyze_device_mobility(device_id)
        if "error" in analysis:
            raise ValueError(analysis["error"])

        df_dev = analysis["processed_df"].copy()
        time_col = (
            "local_created_timestamp"
            if "local_created_timestamp" in df_dev.columns
            else "created_timestamp"
        )

        fig = px.scatter(
            df_dev,
            x=time_col,
            y="displacement_m",
            color=(
                "is_operational_hours"
                if "is_operational_hours" in df_dev.columns
                else "is_within_geofence"
            ),
            color_discrete_map={True: "#2ca02c", False: "#d62728"},
            size="detected_location_accuracy",
            hover_data=["displacement_m"],
            title=f"Displacement Timeline from Facility Boundary — Device: {device_id}",
            labels={time_col: "Local Timestamp", "displacement_m": "Displacement (m)"},
            height=450,
        )
        fig.add_hline(
            y=self.geofence_radius_m,
            line_dash="dash",
            line_color="orange",
            annotation_text=f"Geofence ({int(self.geofence_radius_m)}m)",
        )
        fig.update_layout(template="plotly_white")
        return fig

    def plot_commuter_time_of_day_scatter(self, device_id: str) -> go.Figure:
        """
        Renders a scatter plot mapping Local Hour of Day (0-23) vs Displacement (meters),
        colored by DBSCAN spatial cluster ID.
        """
        analysis = self.analyze_device_mobility(device_id)
        if "error" in analysis:
            fig = go.Figure()
            fig.update_layout(title=f"Error analyzing device: {device_id}")
            return fig

        df_dev = analysis["processed_df"].copy()
        if (
            "local_hour" not in df_dev.columns
            and "local_created_timestamp" in df_dev.columns
        ):
            df_dev["local_hour"] = pd.to_datetime(
                df_dev["local_created_timestamp"]
            ).dt.hour

        df_dev["cluster_str"] = df_dev["cluster_id"].apply(
            lambda x: "Outlier" if x == -1 else f"Cluster {x}"
        )

        fig = px.scatter(
            df_dev,
            x="local_hour",
            y="displacement_m",
            color="cluster_str",
            size="detected_location_accuracy",
            hover_data=["displacement_m", "is_operational_hours"],
            labels={
                "local_hour": "Local Hour of Day (0-23)",
                "displacement_m": "Displacement from School Anchor (m)",
            },
            title=f"Time-of-Day Commuter Pattern — Device: {device_id} ({analysis['mobility_class']})",
        )
        fig.add_hline(
            y=self.geofence_radius_m,
            line_dash="dash",
            line_color="orange",
            annotation_text=f"Geofence ({int(self.geofence_radius_m)}m)",
        )
        fig.update_layout(template="plotly_white", height=450)
        return fig

    def plot_national_mobility_distribution(self) -> go.Figure:
        """
        Renders a national bar chart displaying the distribution of device mobility
        classes (STATIONARY, COMMUTER, RELOCATED, HIGH_MOBILITY).
        """
        report = self.generate_facility_mobility_report()
        if report.empty:
            fig = go.Figure()
            fig.update_layout(title="No mobility records available")
            return fig

        counts = report["mobility_class"].value_counts().reset_index()
        counts.columns = ["mobility_class", "count"]

        fig = px.bar(
            counts,
            x="mobility_class",
            y="count",
            color="mobility_class",
            color_discrete_map={
                "STATIONARY": "#2ca02c",
                "COMMUTER": "#1f77b4",
                "RELOCATED": "#ff7f0e",
                "HIGH_MOBILITY": "#d62728",
            },
            text="count",
            title="National Device Mobility Class Distribution (Pillar 1)",
        )
        fig.update_layout(
            xaxis=dict(title="Mobility Class"),
            yaxis=dict(title="Device Count"),
            template="plotly_white",
            height=400,
            margin=dict(l=10, r=10, t=50, b=30),
        )
        return fig
