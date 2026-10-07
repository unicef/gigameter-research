"""
Module: src/spatial_intelligence/mobility_analyzer.py
Purpose: Pillar 1 device mobility. Classifies each device from its own fix
         events (STATIONARY, COMMUTER, RELOCATED, HIGH_MOBILITY), without
         using a facility centroid, and audits geofence compliance against a
         reference point.
Rules: Settings come from SpatialConfig. Evidence is counted in fix events
       and device-days. DBSCAN labels carry no rank; the dominant cluster is
       the one with the most support.
"""

from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple, Union

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from src.utils.data_loader import TelemetryLoader

from .config import DEFAULT_CONFIG, SpatialConfig
from .fix_events import build_fix_event_table, mark_fix_events
from .geo import NOISE_LABEL, dbscan_labels, haversine_m, weighted_centroid

MOBILITY_CLASSES = ("STATIONARY", "COMMUTER", "RELOCATED", "HIGH_MOBILITY")
REFERENCE_FACILITY_ANCHOR = "facility_anchor"
REFERENCE_DEVICE_DOMINANT = "device_dominant_cluster"


class MobilityAnalyzer:
    """
    Pillar 1 Mobility Engine for GigaMeter telemetry.

    Each device is clustered on its own non-carried fix events. A cluster is
    *supported* when it spans at least `min_cluster_device_days` days;
    unsupported clusters count as noise.

    * `STATIONARY`: one supported cluster and noise share within
      `max_noise_share`.
    * `COMMUTER`: two or more supported clusters, with at least
      `commuter_min_alternations` switches between them over time.
    * `RELOCATED`: two or more supported clusters visited in sequence.
    * `HIGH_MOBILITY`: no supported cluster, or too much noise.

    Geofence compliance is an audit, not an input to the class. It is measured
    against the facility anchor when `facility_summary` is given, otherwise
    against the device's dominant cluster.
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
        geofence_radius_m: Optional[float] = None,
        strategy: Any = None,
        facility_summary: Optional[pd.DataFrame] = None,
        config: SpatialConfig = DEFAULT_CONFIG,
        fix_event_rows: Optional[pd.DataFrame] = None,
    ) -> None:
        """
        Load canonical telemetry and prepare per-device fix events.

        Provide exactly one of `telemetry_df`, `file_path`, or `query_name`.

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
            geofence_radius_m: Overrides `config.geofence_radius_m`.
            strategy: Accepted for compatibility with existing callers; device
                classification does not depend on a cluster strategy.
            facility_summary: Facility anchor table with `school_id_giga`,
                `empirical_centroid_lat`, and `empirical_centroid_lon`. Used
                only for the geofence audit.
            config: Methodology settings.
            fix_event_rows: Output of `mark_fix_events` for the same
                telemetry, to avoid recomputing it.
        """
        if geofence_radius_m is not None:
            config = config.with_overrides(geofence_radius_m=float(geofence_radius_m))
        self.config = config
        self.geofence_radius_m = config.geofence_radius_m

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
        self.valid_geo_df = self.df[
            self.df["detected_latitude"].notna() & self.df["detected_longitude"].notna()
        ].copy()

        self.profiler = None
        self.facility_summary = facility_summary
        self._anchors = self._anchor_lookup(facility_summary)

        if fix_event_rows is None:
            fix_event_rows = mark_fix_events(self.valid_geo_df, config)
        self.fix_event_rows = fix_event_rows
        self.fix_events = build_fix_event_table(fix_event_rows, config, marked=True)

        self._cache: Dict[Tuple[str, float, int], Dict[str, Any]] = {}

    def set_facility_anchors(self, facility_summary: Optional[pd.DataFrame]) -> None:
        """
        Use facility anchors as the geofence reference from now on.

        Device classes do not change; cached results are dropped so the
        audit fields are recomputed against the new reference.
        """
        self.facility_summary = facility_summary
        self._anchors = self._anchor_lookup(facility_summary)
        self._cache.clear()

    @staticmethod
    def _anchor_lookup(
        facility_summary: Optional[pd.DataFrame],
    ) -> Dict[str, Tuple[float, float]]:
        if facility_summary is None or facility_summary.empty:
            return {}
        needed = {"school_id_giga", "empirical_centroid_lat", "empirical_centroid_lon"}
        if not needed.issubset(facility_summary.columns):
            return {}
        valid = facility_summary.dropna(
            subset=["empirical_centroid_lat", "empirical_centroid_lon"]
        )
        return {
            sid: (float(lat), float(lon))
            for sid, lat, lon in zip(
                valid["school_id_giga"],
                valid["empirical_centroid_lat"],
                valid["empirical_centroid_lon"],
            )
        }

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------
    def analyze_device_mobility(
        self,
        device_id: str,
        cluster_eps_m: Optional[float] = None,
        min_samples: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Cluster and classify one device from its non-carried fix events.

        Args:
            device_id: Device to analyse.
            cluster_eps_m: Overrides `config.device_eps_m`.
            min_samples: Overrides `config.device_min_samples` (in fix events).

        Returns:
            A dictionary with the mobility class, cluster and evidence
            counts, the dominant cluster centroid, geofence audit metrics, the
            reference point used for the audit, provenance stamps, and
            `processed_df` (one row per fix event with `cluster_id`,
            `is_supported_cluster`, `is_dominant_cluster`, `displacement_m`,
            and `is_within_geofence`). Returns `{"error": ...}` when the
            device has no valid fix events.
        """
        eps_m = float(cluster_eps_m if cluster_eps_m is not None else self.config.device_eps_m)
        samples = int(min_samples if min_samples is not None else self.config.device_min_samples)
        key = (device_id, eps_m, samples)
        if key in self._cache:
            return self._cache[key]

        events = self.fix_events[self.fix_events["device_id"] == device_id].copy()
        if events.empty:
            return {"error": f"No valid geographic scans found for device_id: {device_id}"}
        events = events.sort_values("first_seen_utc").reset_index(drop=True)
        events["local_date"] = self._event_dates(events)

        events["cluster_id"] = dbscan_labels(
            events["detected_latitude"], events["detected_longitude"], eps_m, samples
        )
        clusters = self._cluster_stats(events)
        supported = clusters[clusters["device_days"] >= self.config.min_cluster_device_days]
        supported_ids = set(supported.index)
        events["is_supported_cluster"] = events["cluster_id"].isin(supported_ids)

        total_events = len(events)
        noise_share = 1.0 - events["is_supported_cluster"].sum() / total_events
        transitions = self._cluster_transitions(events)
        mobility_class = self._classify(len(supported_ids), noise_share, transitions)

        dominant_id = self._dominant_cluster_id(supported)
        events["is_dominant_cluster"] = (
            events["cluster_id"] == dominant_id if dominant_id is not None else False
        )
        dominant_lat, dominant_lon = (np.nan, np.nan)
        if dominant_id is not None:
            members = events[events["is_dominant_cluster"]]
            dominant_lat, dominant_lon = weighted_centroid(
                members["detected_latitude"],
                members["detected_longitude"],
                members.get("detected_location_accuracy"),
                self.config.accuracy_floor_m,
            )

        school_id = events["school_id_giga"].mode().iloc[0]
        school_name = (
            events.loc[events["school_id_giga"] == school_id, "school_name"].dropna().iloc[0]
            if "school_name" in events.columns
            and events.loc[events["school_id_giga"] == school_id, "school_name"].notna().any()
            else school_id
        )

        reference_source = None
        ref_lat, ref_lon = np.nan, np.nan
        if school_id in self._anchors:
            ref_lat, ref_lon = self._anchors[school_id]
            reference_source = REFERENCE_FACILITY_ANCHOR
        elif dominant_id is not None:
            ref_lat, ref_lon = dominant_lat, dominant_lon
            reference_source = REFERENCE_DEVICE_DOMINANT

        events["facility_centroid_lat"] = ref_lat
        events["facility_centroid_lon"] = ref_lon
        if reference_source is not None:
            events["displacement_m"] = haversine_m(
                events["detected_latitude"], events["detected_longitude"], ref_lat, ref_lon
            )
        else:
            events["displacement_m"] = np.nan
        events["is_within_geofence"] = events["displacement_m"] <= self.geofence_radius_m
        compliant = int(events["is_within_geofence"].sum())

        device_rows = self.fix_event_rows[self.fix_event_rows["device_id"] == device_id]
        result = {
            "device_id": device_id,
            "school_id_giga": school_id,
            "school_name": school_name,
            "mobility_class": mobility_class,
            "total_scans": int(len(device_rows)),
            "carried_scans": int(device_rows["fix_carried"].sum()),
            "total_fix_events": total_events,
            "evidence_device_days": int(events["local_date"].nunique()),
            "cluster_count": int(len(clusters)),
            "supported_cluster_count": int(len(supported_ids)),
            "noise_share": round(float(noise_share), 3),
            "cluster_transitions": int(transitions),
            "dominant_cluster_id": dominant_id,
            "dominant_cluster_device_days": (
                int(supported.loc[dominant_id, "device_days"]) if dominant_id is not None else 0
            ),
            "dominant_centroid_lat": dominant_lat,
            "dominant_centroid_lon": dominant_lon,
            "reference_source": reference_source,
            "compliant_scans": compliant,
            "compliance_rate_pct": round(compliant / total_events * 100.0, 1),
            "max_displacement_m": (
                round(float(events["displacement_m"].max()), 1)
                if reference_source is not None
                else np.nan
            ),
            "median_displacement_m": (
                round(float(events["displacement_m"].median()), 1)
                if reference_source is not None
                else np.nan
            ),
            **self.config.provenance(),
            "processed_df": events,
        }
        self._cache[key] = result
        return result

    @staticmethod
    def _event_dates(events: pd.DataFrame) -> pd.Series:
        if "local_date" in events.columns and events["local_date"].notna().all():
            return pd.to_datetime(events["local_date"]).dt.date
        return pd.to_datetime(events["first_seen_utc"]).dt.date

    @staticmethod
    def _cluster_stats(events: pd.DataFrame) -> pd.DataFrame:
        clustered = events[events["cluster_id"] != NOISE_LABEL]
        if clustered.empty:
            return pd.DataFrame(
                columns=["device_days", "events", "first_date", "last_date"]
            )
        return clustered.groupby("cluster_id").agg(
            device_days=("local_date", "nunique"),
            events=("cluster_id", "size"),
            first_date=("local_date", "min"),
            last_date=("local_date", "max"),
        )

    @staticmethod
    def _cluster_transitions(events: pd.DataFrame) -> int:
        sequence = events.loc[events["is_supported_cluster"], "cluster_id"].to_numpy()
        if sequence.size < 2:
            return 0
        return int(np.count_nonzero(sequence[1:] != sequence[:-1]))

    def _classify(self, supported_count: int, noise_share: float, transitions: int) -> str:
        if supported_count == 0:
            return "HIGH_MOBILITY"
        if supported_count == 1:
            return (
                "STATIONARY" if noise_share <= self.config.max_noise_share else "HIGH_MOBILITY"
            )
        if transitions >= self.config.commuter_min_alternations:
            return "COMMUTER"
        return "RELOCATED"

    @staticmethod
    def _dominant_cluster_id(supported: pd.DataFrame) -> Optional[int]:
        if supported.empty:
            return None
        ranked = supported.sort_values(
            by=["device_days", "events", "first_date"], ascending=[False, False, True]
        )
        return int(ranked.index[0])

    # ------------------------------------------------------------------
    # Tables
    # ------------------------------------------------------------------
    def generate_facility_mobility_report(self) -> pd.DataFrame:
        """One row per device: class, evidence, clusters, and geofence audit."""
        results = []
        for device_id in self.fix_events["device_id"].unique():
            metrics = self.analyze_device_mobility(device_id)
            if "error" not in metrics:
                results.append({k: v for k, v in metrics.items() if k != "processed_df"})
        if not results:
            return pd.DataFrame()
        return (
            pd.DataFrame(results)
            .sort_values(by="compliance_rate_pct", ascending=True)
            .reset_index(drop=True)
        )

    def build_device_event_table(self) -> pd.DataFrame:
        """
        All devices' fix events with their cluster labels and device class.

        Returns:
            Concatenated `processed_df` frames with `mobility_class` added.
            Empty when no device has valid fix events.
        """
        frames = []
        for device_id in self.fix_events["device_id"].unique():
            metrics = self.analyze_device_mobility(device_id)
            if "error" in metrics:
                continue
            frame = metrics["processed_df"].copy()
            frame["mobility_class"] = metrics["mobility_class"]
            frames.append(frame)
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    # ------------------------------------------------------------------
    # Plots
    # ------------------------------------------------------------------
    @staticmethod
    def _cluster_label(row: pd.Series) -> str:
        if row["cluster_id"] == NOISE_LABEL:
            return "Noise / Outlier"
        if not row["is_supported_cluster"]:
            return f"Cluster {row['cluster_id']} (unsupported)"
        if row["is_dominant_cluster"]:
            return f"Cluster {row['cluster_id']} (dominant)"
        return f"Cluster {row['cluster_id']}"

    @staticmethod
    def _marker_size(df_dev: pd.DataFrame) -> pd.Series:
        acc = df_dev.get("detected_location_accuracy")
        if acc is None:
            return pd.Series(20.0, index=df_dev.index)
        acc = pd.to_numeric(acc, errors="coerce")
        return acc.fillna(acc.median() if acc.notna().any() else 20.0)

    def _reference_label(self, analysis: Dict[str, Any]) -> str:
        return (
            "Facility Anchor"
            if analysis["reference_source"] == REFERENCE_FACILITY_ANCHOR
            else "Device Dominant Cluster"
        )

    def plot_device_mobility_map(self, device_id: str) -> go.Figure:
        """Map 1: Device fix events coloured by DBSCAN cluster, with the reference point."""
        analysis = self.analyze_device_mobility(device_id)
        if "error" in analysis:
            raise ValueError(analysis["error"])

        df_dev = analysis["processed_df"].copy()
        df_dev["cluster_label"] = df_dev.apply(self._cluster_label, axis=1)
        df_dev["marker_size"] = self._marker_size(df_dev)

        hover = [c for c in ("device_id", "displacement_m", "detected_location_accuracy",
                             "detected_wifi_ssid", "row_count", "is_operational_hours")
                 if c in df_dev.columns]
        fig = px.scatter_mapbox(
            df_dev,
            lat="detected_latitude",
            lon="detected_longitude",
            color="cluster_label",
            size="marker_size",
            size_max=15,
            hover_data=hover,
            title=f"Pillar 1 Spatial Mobility Audit - Device: {device_id} ({analysis['mobility_class']})",
            zoom=13,
            height=650,
        )
        if analysis["reference_source"] is not None:
            label = self._reference_label(analysis)
            fig.add_trace(
                go.Scattermapbox(
                    lat=[df_dev["facility_centroid_lat"].iloc[0]],
                    lon=[df_dev["facility_centroid_lon"].iloc[0]],
                    mode="markers+text",
                    marker=dict(size=18, color="red"),
                    text=[label],
                    textposition="top center",
                    name=label,
                )
            )
        fig.update_layout(mapbox_style="open-street-map", margin=dict(l=10, r=10, t=50, b=10))
        return fig

    def plot_displacement_timeline(self, device_id: str) -> go.Figure:
        """Map 2: Distance of each fix event from the reference point over time."""
        analysis = self.analyze_device_mobility(device_id)
        if "error" in analysis:
            raise ValueError(analysis["error"])

        df_dev = analysis["processed_df"].copy()
        df_dev["marker_size"] = self._marker_size(df_dev)
        time_col = (
            "local_created_timestamp" if "local_created_timestamp" in df_dev.columns else "first_seen_utc"
        )
        color_col = "is_operational_hours" if "is_operational_hours" in df_dev.columns else "is_within_geofence"
        fig = px.scatter(
            df_dev,
            x=time_col,
            y="displacement_m",
            color=color_col,
            color_discrete_map={True: "#2ca02c", False: "#d62728"},
            size="marker_size",
            hover_data=["displacement_m"],
            title=(
                f"Displacement from {self._reference_label(analysis)} - Device: {device_id}"
            ),
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
        """Local hour of day against displacement, coloured by DBSCAN cluster."""
        analysis = self.analyze_device_mobility(device_id)
        if "error" in analysis:
            fig = go.Figure()
            fig.update_layout(title=f"Error analyzing device: {device_id}")
            return fig

        df_dev = analysis["processed_df"].copy()
        if "local_hour" not in df_dev.columns and "local_created_timestamp" in df_dev.columns:
            df_dev["local_hour"] = pd.to_datetime(df_dev["local_created_timestamp"]).dt.hour
        df_dev["cluster_str"] = df_dev.apply(self._cluster_label, axis=1)
        df_dev["marker_size"] = self._marker_size(df_dev)

        hover = [c for c in ("displacement_m", "is_operational_hours") if c in df_dev.columns]
        fig = px.scatter(
            df_dev,
            x="local_hour",
            y="displacement_m",
            color="cluster_str",
            size="marker_size",
            hover_data=hover,
            labels={
                "local_hour": "Local Hour of Day (0-23)",
                "displacement_m": f"Displacement from {self._reference_label(analysis)} (m)",
            },
            title=f"Time-of-Day Commuter Pattern - Device: {device_id} ({analysis['mobility_class']})",
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
        """Bar chart of device counts per mobility class."""
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
