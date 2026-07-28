"""
Module: src/mobility_analyzer.py
Purpose: Pillar 1 Entity Geofencing, DBSCAN Spatial Mobility Clustering, 
         and Interactive Plotly Visualizations for GigaMeter Telemetry.
Rules: Aligned with GigaMeter Technical Specs v2.2 (08:00 - 19:59 Operational Window).
"""

import numpy as np
import pandas as pd
from typing import Optional, Dict, Any
from sklearn.cluster import DBSCAN
import plotly.express as px
import plotly.graph_objects as go

from src.spatial_profiler import SpatialProfiler, haversine_distance_meters


class MobilityAnalyzer:
    """
    Pillar 1 Mobility Engine for GigaMeter Telemetry.
    Performs device-level geofencing audits, DBSCAN spatial clustering,
    behavioral classification, and interactive Plotly spatial mapping.
    """

    def __init__(
        self, 
        telemetry_df: pd.DataFrame, 
        schools_df: Optional[pd.DataFrame] = None,
        geofence_radius_m: float = 200.0
    ):
        self.df = telemetry_df.copy()
        self.geofence_radius_m = geofence_radius_m
        
        # Standardize primary field names
        if "giga_id_school" in self.df.columns:
            self.df = self.df.rename(columns={"giga_id_school": "school_id_giga"})
        if "device_hardware_id" in self.df.columns:
            self.df = self.df.rename(columns={"device_hardware_id": "device_id"})
            
        # Ensure strict No-IP fallback policy: filter out missing coordinates
        self.valid_geo_df = self.df[
            self.df["detected_latitude"].notna() & self.df["detected_longitude"].notna()
        ].copy()

        # Build empirical facility centroids via SpatialProfiler
        self.profiler = SpatialProfiler(self.valid_geo_df)
        self.facility_summary = self.profiler.build_facility_spatial_summary(schools_df=schools_df)
        
        # Map empirical centroid back onto measurement records
        centroid_map_lat = dict(zip(self.facility_summary["school_id_giga"], self.facility_summary["empirical_centroid_lat"]))
        centroid_map_lon = dict(zip(self.facility_summary["school_id_giga"], self.facility_summary["empirical_centroid_lon"]))
        
        self.valid_geo_df["facility_centroid_lat"] = self.valid_geo_df["school_id_giga"].map(centroid_map_lat)
        self.valid_geo_df["facility_centroid_lon"] = self.valid_geo_df["school_id_giga"].map(centroid_map_lon)

        # Calculate instantaneous displacement (meters) from empirical school centroid
        self.valid_geo_df["displacement_m"] = self.valid_geo_df.apply(
            lambda r: haversine_distance_meters(
                r["detected_latitude"], r["detected_longitude"],
                r["facility_centroid_lat"], r["facility_centroid_lon"]
            ), axis=1
        )
        
        # Flag geofence compliance per ping
        self.valid_geo_df["is_within_geofence"] = self.valid_geo_df["displacement_m"] <= self.geofence_radius_m

    def analyze_device_mobility(
        self, 
        device_id: str, 
        cluster_eps_m: float = 150.0, 
        min_samples: int = 3
    ) -> Dict[str, Any]:
        """
        Analyzes a single device's trajectory using DBSCAN clustering.
        Classifies behavior as: STATIONARY, COMMUTER, RELOCATED, or HIGH_MOBILITY.
        """
        device_data = self.valid_geo_df[self.valid_geo_df["device_id"] == device_id].copy()
        
        if device_data.empty:
            return {"error": f"No valid geographic scans found for device_id: {device_id}"}

        school_id = device_data["school_id_giga"].iloc[0]
        school_name = device_data["school_name"].iloc[0] if "school_name" in device_data.columns else school_id
        
        # Sort chronologically
        timestamp_col = "local_created_timestamp" if "local_created_timestamp" in device_data.columns else "created_timestamp"
        device_data = device_data.sort_values(by=timestamp_col)

        # -------------------------------------------------------------------
        # Step 1: DBSCAN Spatial Clustering (Haversine Metric)
        # -------------------------------------------------------------------
        coords_rad = np.radians(device_data[["detected_latitude", "detected_longitude"]].values)
        kms_per_radian = 6371.0088
        eps_rad = (cluster_eps_m / 1000.0) / kms_per_radian

        db = DBSCAN(eps=eps_rad, min_samples=min_samples, metric="haversine").fit(coords_rad)
        device_data["cluster_id"] = db.labels_

        unique_clusters = set(db.labels_) - {-1}  # Exclude noise (-1)
        cluster_count = len(unique_clusters)
        total_scans = len(device_data)
        compliant_scans = int(device_data["is_within_geofence"].sum())
        compliance_rate_pct = round((compliant_scans / total_scans) * 100.0, 1)

        # -------------------------------------------------------------------
        # Step 2: Behavioral Classification Engine
        # -------------------------------------------------------------------
        mobility_class = "STATIONARY"
        
        if cluster_count <= 1 and compliance_rate_pct >= 90.0:
            mobility_class = "STATIONARY"
        elif cluster_count >= 2:
            # Check temporal distribution across clusters
            device_data["date"] = pd.to_datetime(device_data[timestamp_col]).dt.date
            
            # Group clusters by min and max date to detect sequential relocation
            cluster_dates = device_data[device_data["cluster_id"] != -1].groupby("cluster_id")["date"].agg(["min", "max"])
            
            # Check if clusters are strictly sequential in time (Relocated)
            is_sequential = False
            cluster_ids = list(cluster_dates.index)
            if len(cluster_ids) == 2:
                c0_max = cluster_dates.loc[cluster_ids[0], "max"]
                c1_min = cluster_dates.loc[cluster_ids[1], "min"]
                if c0_max < c1_min or cluster_dates.loc[cluster_ids[1], "max"] < cluster_dates.loc[cluster_ids[0], "min"]:
                    is_sequential = True

            if is_sequential:
                mobility_class = "RELOCATED"
            else:
                # Check operational hour distribution (Commuter vs High Mobility)
                if "is_operational_hours" in device_data.columns:
                    # Off-hours presence in secondary cluster
                    off_hour_scans = device_data[~device_data["is_operational_hours"]]
                    if not off_hour_scans.empty and (off_hour_scans["cluster_id"] != 0).any():
                        mobility_class = "COMMUTER"
                    else:
                        mobility_class = "HIGH_MOBILITY"
                else:
                    mobility_class = "COMMUTER"
        elif compliance_rate_pct < 50.0:
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
            "median_displacement_m": round(float(device_data["displacement_m"].median()), 1),
            "processed_df": device_data
        }

    def generate_facility_mobility_report(self) -> pd.DataFrame:
        """
        Generates a facility-wide mobility audit for all registered devices.
        """
        results = []
        for device_id in self.valid_geo_df["device_id"].unique():
            metrics = self.analyze_device_mobility(device_id)
            if "error" not in metrics:
                # Omit processed_df dataframe for clean summary table
                metrics_summary = {k: v for k, v in metrics.items() if k != "processed_df"}
                results.append(metrics_summary)
                
        summary_df = pd.DataFrame(results)
        return summary_df.sort_values(by="compliance_rate_pct", ascending=True).reset_index(drop=True)

    # -------------------------------------------------------------------
    # INTERACTIVE PLOTLY VISUALIZATION METHODS
    # -------------------------------------------------------------------
    def plot_device_mobility_map(self, device_id: str) -> go.Figure:
        """
        Map 1: Interactive Plotly Mapbox Spatial Cluster Visualization.
        Renders device pings color-coded by DBSCAN cluster ID, with the 
        empirical school centroid and geofence boundary cleanly overlaid.
        """
        analysis = self.analyze_device_mobility(device_id)
        if "error" in analysis:
            raise ValueError(analysis["error"])

        df_dev = analysis["processed_df"].copy()
        school_lat = df_dev["facility_centroid_lat"].iloc[0]
        school_lon = df_dev["facility_centroid_lon"].iloc[0]

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
                "device_id", "displacement_m", "detected_location_accuracy", 
                "is_operational_hours", "detected_wifi_ssid"
            ],
            title=f"Pillar 1 Spatial Mobility Audit — Device: {device_id} ({analysis['mobility_class']})",
            zoom=13,
            height=650
        )

        # Overlay Empirical School Centroid
        fig.add_trace(
            go.Scattermapbox(
                lat=[school_lat],
                lon=[school_lon],
                mode="markers+text",
                marker=dict(size=18, color="red", symbol="hospital"),
                text=["School Facility Centroid"],
                textposition="top center",
                name="Facility Anchor"
            )
        )

        fig.update_layout(
            mapbox_style="open-street-map",
            margin=dict(l=10, r=10, t=50, b=10),
            legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01)
        )
        return fig

    def plot_displacement_timeline(self, device_id: str) -> go.Figure:
        """
        Map 2: Interactive Displacement Timeline (Distance from Centroid over Time).
        Visually separates commuters (oscillating distance) from permanent shifts.
        """
        analysis = self.analyze_device_mobility(device_id)
        if "error" in analysis:
            raise ValueError(analysis["error"])

        df_dev = analysis["processed_df"].copy()
        time_col = "local_created_timestamp" if "local_created_timestamp" in df_dev.columns else "created_timestamp"

        fig = px.scatter(
            df_dev,
            x=time_col,
            y="displacement_m",
            color="is_operational_hours" if "is_operational_hours" in df_dev.columns else "is_within_geofence",
            color_discrete_map={True: "#2ca02c", False: "#d62728"},
            size="detected_location_accuracy",
            hover_data=["detected_wifi_ssid", "detected_wifi_bssid", "displacement_m"],
            title=f"Displacement Timeline from Facility Boundary — Device: {device_id}",
            labels={
                time_col: "Device Local Timestamp",
                "displacement_m": "Displacement from Centroid (meters)",
                "is_operational_hours": "Active Operational Hours (08:00-19:59)"
            },
            height=450
        )

        # Add Geofence Radius Reference Threshold Line
        fig.add_hline(
            y=self.geofence_radius_m, 
            line_dash="dash", 
            line_color="orange",
            annotation_text=f"Geofence Boundary ({int(self.geofence_radius_m)}m)",
            annotation_position="bottom right"
        )

        fig.update_layout(template="plotly_white")
        return fig