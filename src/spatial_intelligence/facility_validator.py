"""
Module: src/spatial_intelligence/facility_validator.py
Purpose: Multi-track facility audit. Track 1 (location truth), Track 2
         (hardware integrity), and Track 3 (entity attribution), built on
         device mobility and the facility anchor.
Rules: Device mobility runs first, then anchor selection, then scoring. The
       raw score is computed on the anchor cluster only. Track 1 flags are
       set by distance; confidence is a separate tier. Tracks never share
       a flag.
"""

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from src.utils.data_loader import (
    TelemetryLoader,
    _delta_store_or_default,
    prepare_schools_frame,
)

from .config import DEFAULT_CONFIG, STRATEGY_TELEMETRY_DOMINANCE, SpatialConfig
from .geo import haversine_m, max_pairwise_distance_m
from .mobility_analyzer import MobilityAnalyzer
from .palette import (
    ACTION_COLORS,
    ACTION_ORDER,
    ANCHOR_COLOR,
    CANDIDATE_COLOR,
    CONFIDENCE_COLORS,
    CONFIDENCE_ORDER,
    FLAG_ORDER,
    GEOFENCE_COLOR,
    GOVT_PIN_COLOR,
    MOBILITY_COLORS,
    NOISE_COLOR,
    OTHER_ENTITY_COLOR,
)
from .plot_utils import add_log_x_vline
from .spatial_profiler import RESOLVED_BY_NAME_MATCH, RESOLVED_BY_UNRESOLVED, SpatialProfiler

FLAG_VERIFIED = "VERIFIED_ACCURATE"
FLAG_DISPERSION = "CAMPUS_DISPERSION"
FLAG_MISMATCH = "GOVT_PIN_MISMATCH"
FLAG_AMBIGUOUS = "AMBIGUOUS_MULTI_CLUSTER"
FLAG_UNSTABLE = "UNSTABLE_MOBILE_ONLY"
FLAG_NO_PIN = "NO_GOVT_PIN_AVAILABLE"
FLAG_INSUFFICIENT = "INSUFFICIENT_DATA"

ACTION_SUBMIT = "SUBMIT_CORRECTION"
ACTION_FIELD_VERIFY = "FIELD_VERIFY"
ACTION_AWAIT = "AWAIT_DATA"
ACTION_NONE = "NONE"

ATTRIBUTION_CONSISTENT = "CONSISTENT"
ATTRIBUTION_OTHER_NEARBY = "OTHER_ENTITY_NEARBY"
ATTRIBUTION_UNRESOLVED = "UNRESOLVED"

PINS_FROM_TABLE = "entity_pins"
PINS_FROM_DELTA = "delta_sharing"
PINS_FROM_TELEMETRY = "telemetry_pins"

MOBILITY_COUNT_KEYS = {
    "STATIONARY": "stationary",
    "COMMUTER": "commuter",
    "RELOCATED": "relocated",
    "HIGH_MOBILITY": "high_mobility",
    "INSUFFICIENT_EVIDENCE": "insufficient_evidence",
}


def _linear_points(value: float, full_at: float, zero_at: float, max_points: float) -> float:
    """`max_points` at or below `full_at`, zero at or above `zero_at`, linear between."""
    if pd.isna(value):
        return 0.0
    if value <= full_at:
        return max_points
    if value >= zero_at:
        return 0.0
    return max_points * (1.0 - (value - full_at) / (zero_at - full_at))


class FacilityValidator:
    """
    Multi-track facility audit for GigaMeter telemetry.

    The chain runs once at construction: `SpatialProfiler` tags hotspots and
    builds fix events, `MobilityAnalyzer` classifies devices,
    `SpatialProfiler` selects each facility's anchor, and the mobility
    geofence audit is pointed at the anchors.

    * Track 1, location truth: anchor distance to the official pin, a
      confidence tier from S_raw, and a recommended action.
    * Track 2, hardware integrity: S_raw x P_coherence and anomaly tags.
    * Track 3, entity attribution: registry name match and the nearest
      official pin of another entity.
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
        strategies: Optional[Sequence[str]] = None,
        config: SpatialConfig = DEFAULT_CONFIG,
        entity_pins: Optional[pd.DataFrame] = None,
        load_entity_pins: bool = False,
    ) -> None:
        """
        Load canonical telemetry and build the facility audit.

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
            strategies: Overrides `config.strategies`.
            config: Methodology settings.
            entity_pins: Country table of official pins for Track 3, with
                `school_id_giga` (or `giga_id_school`), `latitude`, and
                `longitude`.
            load_entity_pins: Load the Track 3 table from Delta Sharing with
                `country_iso3` when `entity_pins` is not given.

        Raises:
            ValueError: If `load_entity_pins` is set without `country_iso3`.
        """
        overrides: Dict[str, Any] = {}
        if geofence_radius_m is not None:
            overrides["geofence_radius_m"] = float(geofence_radius_m)
        if strategies is not None:
            overrides["strategies"] = tuple(strategies)
        self.config = config.with_overrides(**overrides) if overrides else config
        self.geofence_radius_m = self.config.geofence_radius_m

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

        self.spatial_profiler = SpatialProfiler(self.valid_geo_df, config=self.config)
        self.mobility_analyzer = MobilityAnalyzer(
            telemetry_df=self.valid_geo_df,
            config=self.config,
            fix_event_rows=self.spatial_profiler.fix_event_rows,
        )
        self.facility_summary = self.spatial_profiler.build_facility_spatial_summary(
            device_events=self.mobility_analyzer.build_device_event_table()
        )
        self.mobility_analyzer.set_facility_anchors(self.facility_summary)
        self.facility_clusters = self.spatial_profiler.facility_clusters
        self.facility_events = self.spatial_profiler.facility_events

        if entity_pins is not None:
            self.entity_pins = prepare_schools_frame(entity_pins)
            self.entity_pins_source = PINS_FROM_TABLE
        elif load_entity_pins:
            if not country_iso3:
                raise ValueError("load_entity_pins requires country_iso3.")
            store = _delta_store_or_default(delta_store)
            self.entity_pins = prepare_schools_frame(store.load_table(country_iso3))
            self.entity_pins_source = PINS_FROM_DELTA
        else:
            pin_columns = ["school_id_giga", "govt_latitude", "govt_longitude"]
            self.entity_pins = (
                self.facility_summary[pin_columns].reset_index(drop=True)
                if not self.facility_summary.empty
                else pd.DataFrame(columns=pin_columns)
            )
            self.entity_pins_source = PINS_FROM_TELEMETRY
        self.entity_pins = self.entity_pins.dropna(subset=["govt_latitude", "govt_longitude"])

        self._summary_by_id = (
            self.facility_summary.set_index("school_id_giga", drop=False)
            if not self.facility_summary.empty
            else pd.DataFrame(columns=["school_id_giga"]).set_index("school_id_giga")
        )
        self._evaluation_cache: Dict[str, Dict[str, Any]] = {}
        self._national_audit_cache: Optional[pd.DataFrame] = None

    # ------------------------------------------------------------------
    # Evidence helpers
    # ------------------------------------------------------------------
    def _score_cluster_id(self, summary: pd.Series) -> Optional[int]:
        if pd.notna(summary["anchor_cluster_id"]):
            return int(summary["anchor_cluster_id"])
        candidates = summary["strategy_candidates"] or {}
        if STRATEGY_TELEMETRY_DOMINANCE in candidates:
            return int(candidates[STRATEGY_TELEMETRY_DOMINANCE])
        return int(next(iter(candidates.values()))) if candidates else None

    def _cluster_events(self, school_id: str, cluster_id: Optional[int]) -> pd.DataFrame:
        events = self.facility_events
        if cluster_id is None or events is None or events.empty:
            return pd.DataFrame()
        return events[
            (events["school_id_giga"] == school_id) & (events["facility_cluster_id"] == cluster_id)
        ]

    def _device_results(self, device_ids: List[str]) -> List[Dict[str, Any]]:
        results = []
        for device_id in device_ids:
            result = self.mobility_analyzer.analyze_device_mobility(device_id)
            if "error" not in result:
                results.append(result)
        return results

    def _raw_score(self, events: pd.DataFrame, devices: List[Dict[str, Any]]) -> Dict[str, float]:
        cfg = self.config
        if events.empty:
            return {"stability": 0.0, "consensus": 0.0, "bssid": 0.0, "depth": 0.0, "precision": 0.0}

        classes = {d["mobility_class"] for d in devices}
        stationary, commuter, other = cfg.stability_points
        stability = stationary if "STATIONARY" in classes else (commuter if "COMMUTER" in classes else other)

        centroids = [
            (d["dominant_centroid_lat"], d["dominant_centroid_lon"])
            for d in devices
            if d["dominant_cluster_id"] is not None
        ]
        if len(centroids) > 1:
            lats, lons = zip(*centroids)
            consensus = _linear_points(
                max_pairwise_distance_m(lats, lons),
                cfg.consensus_full_m,
                cfg.consensus_zero_m,
                cfg.consensus_max,
            )
        else:
            consensus = cfg.consensus_single_device

        full_bssid, partial_bssid = cfg.bssid_points
        fixed = events[events["detected_wifi_bssid"].notna()]
        if "is_mobile_hotspot" in fixed.columns:
            fixed = fixed[~fixed["is_mobile_hotspot"].astype(bool)]
        best_days = fixed.groupby("detected_wifi_bssid")["local_date"].nunique().max() if not fixed.empty else 0
        bssid = full_bssid if best_days >= cfg.bssid_full_days else partial_bssid

        device_days = events[["device_id", "local_date"]].drop_duplicates().shape[0]
        depth = min(cfg.depth_max, cfg.depth_max * device_days / cfg.depth_full_device_days)

        accuracy = pd.to_numeric(events.get("detected_location_accuracy"), errors="coerce")
        precision = _linear_points(
            float(accuracy.mean()) if accuracy is not None and accuracy.notna().any() else np.nan,
            cfg.precision_full_m,
            cfg.precision_zero_m,
            cfg.precision_max,
        )
        return {
            "stability": round(stability, 1),
            "consensus": round(consensus, 1),
            "bssid": round(bssid, 1),
            "depth": round(depth, 1),
            "precision": round(precision, 1),
        }

    def _confidence_level(self, score: float) -> str:
        if score >= self.config.confidence_high_min:
            return "HIGH"
        if score >= self.config.confidence_medium_min:
            return "MEDIUM"
        return "LOW"

    def _location_flag(self, summary: pd.Series) -> str:
        cfg = self.config
        if summary["facility_device_days"] < cfg.min_support_device_days:
            return FLAG_INSUFFICIENT
        if summary["anchor_resolved_by"] == RESOLVED_BY_UNRESOLVED:
            return FLAG_AMBIGUOUS
        if not summary["anchor_supported"]:
            return FLAG_UNSTABLE
        if pd.isna(summary["govt_displacement_m"]):
            return FLAG_NO_PIN
        distance = summary["govt_displacement_m"]
        if distance <= cfg.verified_max_m:
            return FLAG_VERIFIED
        if distance <= cfg.mismatch_min_m:
            return FLAG_DISPERSION
        return FLAG_MISMATCH

    @staticmethod
    def _recommended_action(flag: str, level: str, anchor_devices: int) -> str:
        if flag in (FLAG_INSUFFICIENT, FLAG_UNSTABLE):
            return ACTION_AWAIT
        if flag == FLAG_AMBIGUOUS:
            return ACTION_FIELD_VERIFY
        if level == "LOW":
            return ACTION_AWAIT
        if flag == FLAG_VERIFIED:
            return ACTION_NONE
        if flag == FLAG_MISMATCH and level == "HIGH" and anchor_devices >= 2:
            return ACTION_SUBMIT
        return ACTION_FIELD_VERIFY

    def _p_coherence(self, split_m: float) -> float:
        cfg = self.config
        if split_m <= cfg.coherence_full_m:
            return 1.0
        if split_m <= cfg.split_m:
            return 1.0 - 0.5 * (split_m - cfg.coherence_full_m) / (cfg.split_m - cfg.coherence_full_m)
        return cfg.coherence_floor

    def _entity_attribution(self, school_id: str, summary: pd.Series) -> Dict[str, Any]:
        result = {
            "entity_attribution_flag": ATTRIBUTION_UNRESOLVED,
            "nearest_other_entity_id": None,
            "nearest_other_entity_distance_m": np.nan,
            "entity_pins_source": self.entity_pins_source,
        }
        name_match = bool(summary["ssid_name_match"])
        lat, lon = summary["empirical_centroid_lat"], summary["empirical_centroid_lon"]
        if pd.isna(lat) or pd.isna(lon):
            return result

        others = self.entity_pins[self.entity_pins["school_id_giga"] != school_id]
        if not others.empty:
            distances = haversine_m(others["govt_latitude"], others["govt_longitude"], lat, lon)
            nearest = int(np.argmin(distances))
            result["nearest_other_entity_id"] = others["school_id_giga"].iloc[nearest]
            result["nearest_other_entity_distance_m"] = round(float(distances[nearest]), 1)

        own = summary["govt_displacement_m"]
        other = result["nearest_other_entity_distance_m"]
        own_is_nearest = (
            pd.notna(own)
            and own <= self.config.mismatch_min_m
            and (pd.isna(other) or own <= other)
        )
        if name_match or own_is_nearest:
            result["entity_attribution_flag"] = ATTRIBUTION_CONSISTENT
        elif pd.notna(other) and other <= self.config.other_entity_radius_m:
            result["entity_attribution_flag"] = ATTRIBUTION_OTHER_NEARBY
        return result

    @staticmethod
    def _round_or_nan(value: Any, digits: int) -> float:
        return round(float(value), digits) if pd.notna(value) else np.nan

    # ------------------------------------------------------------------
    # Facility evaluation
    # ------------------------------------------------------------------
    def evaluate_facility_location_confidence(self, school_id_giga: str) -> Dict[str, Any]:
        """
        Evaluate one facility on all tracks.

        Returns:
            Track 1 (`location_verification_flag`,
            `location_confidence_score`, `location_confidence_level`,
            `recommended_action`, distances and anchor fields), Track 2
            (`hardware_health_score`, `p_coherence`, `split_distance_m`,
            `hardware_anomaly_tags`), Track 3 (`entity_attribution_flag`,
            `ssid_name_match`, nearest other entity), device mobility
            counts, `score_breakdown`, and provenance.
        """
        if school_id_giga in self._evaluation_cache:
            return self._evaluation_cache[school_id_giga]
        cfg = self.config

        if school_id_giga not in self._summary_by_id.index:
            result = {
                "school_id_giga": school_id_giga,
                "school_name": school_id_giga,
                "location_confidence_score": 0.0,
                "location_confidence_level": "LOW",
                "location_verification_flag": FLAG_INSUFFICIENT,
                "recommended_action": ACTION_AWAIT,
                "hardware_health_score": 0.0,
                "hardware_anomaly_tags": [],
                "entity_attribution_flag": ATTRIBUTION_UNRESOLVED,
                "reason": "No valid fix events for this facility.",
                "total_scans": 0,
                "distinct_devices": 0,
                **{f"{key}_devices_count": 0 for key in MOBILITY_COUNT_KEYS.values()},
                **cfg.provenance(),
            }
            self._evaluation_cache[school_id_giga] = result
            return result

        summary = self._summary_by_id.loc[school_id_giga]
        facility_devices = sorted(
            self.valid_geo_df.loc[self.valid_geo_df["school_id_giga"] == school_id_giga, "device_id"]
            .dropna()
            .unique()
        )
        device_results = self._device_results(facility_devices)
        classes = [d["mobility_class"] for d in device_results]
        counts = {key: classes.count(cls) for cls, key in MOBILITY_COUNT_KEYS.items()}

        score_cluster = self._score_cluster_id(summary)
        cluster_events = self._cluster_events(school_id_giga, score_cluster)
        cluster_devices = (
            sorted(cluster_events["device_id"].dropna().unique()) if not cluster_events.empty else []
        )
        contributing = [d for d in device_results if d["device_id"] in set(cluster_devices)]

        breakdown = self._raw_score(cluster_events, contributing)
        raw_score = round(sum(breakdown.values()), 1)
        level = self._confidence_level(raw_score)
        flag = self._location_flag(summary)
        action = self._recommended_action(flag, level, len(cluster_devices))

        split_m = float(summary["split_distance_m"])
        p_coherence = self._p_coherence(split_m)
        tags = []
        if split_m > cfg.split_m:
            tags.append("BSSID_SPATIAL_SPLIT")
        if summary["hotspot_event_pct"] >= cfg.hotspot_share_min * 100.0:
            tags.append("HOTSPOT_TETHERED_FACILITY")
        if any(d["mobility_class"] == "COMMUTER" for d in contributing):
            tags.append("COMMUTER_DEVICE")
        if counts["relocated"] > 0:
            tags.append("RELOCATED_DEVICE")

        result = {
            "school_id_giga": school_id_giga,
            "school_name": summary["school_name"],
            # Track 1
            "location_verification_flag": flag,
            "location_confidence_score": raw_score,
            "location_confidence_level": level,
            "recommended_action": action,
            "govt_displacement_m": self._round_or_nan(summary["govt_displacement_m"], 1),
            "candidate_govt_displacement_m": summary["candidate_govt_displacement_m"],
            "empirical_latitude": self._round_or_nan(summary["empirical_centroid_lat"], 6),
            "empirical_longitude": self._round_or_nan(summary["empirical_centroid_lon"], 6),
            "govt_latitude": self._round_or_nan(summary["govt_latitude"], 6),
            "govt_longitude": self._round_or_nan(summary["govt_longitude"], 6),
            "anchor_cluster_id": (
                int(summary["anchor_cluster_id"]) if pd.notna(summary["anchor_cluster_id"]) else None
            ),
            "anchor_supported": bool(summary["anchor_supported"]),
            "anchor_bssids": summary["anchor_bssids"],
            "anchor_support_device_days": int(summary["anchor_support_device_days"]),
            "anchor_support_devices": int(summary["anchor_support_devices"]),
            "score_cluster_id": score_cluster,
            "strategy_candidates": summary["strategy_candidates"],
            "strategy_agreement": bool(summary["strategy_agreement"]),
            "anchor_resolved_by": summary["anchor_resolved_by"],
            "strategy_fallback_reason": (
                summary["strategy_fallback_reason"] if pd.notna(summary["strategy_fallback_reason"]) else None
            ),
            # Track 2
            "hardware_health_score": round(raw_score * p_coherence, 1),
            "hardware_anomaly_tags": tags,
            "p_coherence": round(p_coherence, 2),
            "split_distance_m": round(split_m, 1),
            "hotspot_event_pct": summary["hotspot_event_pct"],
            # Track 3
            "ssid_name_match": bool(summary["ssid_name_match"]),
            **self._entity_attribution(school_id_giga, summary),
            # Devices and evidence
            "distinct_devices": len(facility_devices),
            **{f"{key}_devices_count": value for key, value in counts.items()},
            "device_mobility_counts": counts,
            "total_scans": int(summary["total_valid_geo_records"]),
            "total_fix_events": int(summary["total_fix_events"]),
            "facility_device_days": int(summary["facility_device_days"]),
            "mean_accuracy_m": self._round_or_nan(summary["mean_accuracy_m"], 1),
            "score_breakdown": breakdown,
            **cfg.provenance(),
        }
        self._evaluation_cache[school_id_giga] = result
        return result

    def run_national_facility_audit(self, force_refresh: bool = False) -> pd.DataFrame:
        """
        Evaluate every facility, one row each, cached after the first call.

        `score_breakdown` is flattened into `score_<component>` columns,
        `hardware_anomaly_tags` is joined into a string (`NONE` when empty),
        and `device_mobility_counts` is dropped in favour of the
        `*_devices_count` columns.
        """
        if self._national_audit_cache is not None and not force_refresh:
            return self._national_audit_cache

        results = []
        for school_id in self.valid_geo_df["school_id_giga"].unique():
            res = dict(self.evaluate_facility_location_confidence(school_id))
            for key, value in res.pop("score_breakdown", {}).items():
                res[f"score_{key}"] = value
            res.pop("device_mobility_counts", None)
            res["hardware_anomaly_tags"] = ", ".join(res["hardware_anomaly_tags"]) or "NONE"
            results.append(res)

        audit_df = pd.DataFrame(results)
        if not audit_df.empty:
            audit_df = audit_df.sort_values(by="location_confidence_score", ascending=False).reset_index(
                drop=True
            )
        self._national_audit_cache = audit_df
        return audit_df

    def summarize_national_audit(self) -> Dict[str, Any]:
        """
        Summarize the cached national audit for the executive metric cards.

        Stationary facilities are those whose scoring cluster includes a
        `STATIONARY` device (`score_stability` at its maximum). Percentages
        and the mean hardware score are rounded to one decimal; an empty
        audit returns zeros.

        Returns:
            Facility counts per Track 1 flag and recommended action,
            stationary-hardware share, anomaly-tag counts, strategy
            agreement share, Track 3 counts, and the mean hardware score.
        """
        audit_df = self.run_national_facility_audit()
        flag_keys = {
            FLAG_VERIFIED: "verified_accurate",
            FLAG_MISMATCH: "govt_pin_mismatch",
            FLAG_DISPERSION: "campus_dispersion",
            FLAG_AMBIGUOUS: "ambiguous_multi_cluster",
            FLAG_UNSTABLE: "unstable_mobile_only",
            FLAG_NO_PIN: "no_govt_pin_available",
            FLAG_INSUFFICIENT: "insufficient_data",
        }
        action_keys = {
            ACTION_SUBMIT: "submit_correction",
            ACTION_FIELD_VERIFY: "field_verify",
            ACTION_AWAIT: "await_data",
            ACTION_NONE: "no_action",
        }
        summary: Dict[str, Any] = {
            "total_facilities": 0,
            **{key: 0 for key in flag_keys.values()},
            **{key: 0 for key in action_keys.values()},
            "stationary_facilities": 0,
            "stationary_pct": 0.0,
            "bssid_spatial_splits": 0,
            "hotspot_tethered_facilities": 0,
            "commuter_device_facilities": 0,
            "relocated_device_facilities": 0,
            "coherence_penalised": 0,
            "confidence_high": 0,
            "confidence_medium": 0,
            "confidence_low": 0,
            "strategy_agreement_pct": 0.0,
            "resolved_by_name_match": 0,
            "attribution_consistent": 0,
            "other_entity_nearby": 0,
            "attribution_unresolved": 0,
            "mean_hardware_health_score": 0.0,
            **self.config.provenance(),
        }
        if audit_df.empty:
            return summary

        total = len(audit_df)
        flags = audit_df["location_verification_flag"]
        actions = audit_df["recommended_action"]
        tags = audit_df["hardware_anomaly_tags"]
        levels = audit_df["location_confidence_level"]
        attribution = audit_df["entity_attribution_flag"]
        stationary = int((audit_df["score_stability"] == self.config.stability_points[0]).sum())
        summary.update({key: int((flags == flag).sum()) for flag, key in flag_keys.items()})
        summary.update({key: int((actions == action).sum()) for action, key in action_keys.items()})
        summary.update(
            {
                "total_facilities": total,
                "stationary_facilities": stationary,
                "stationary_pct": round(stationary / total * 100.0, 1),
                "bssid_spatial_splits": int(tags.str.contains("BSSID_SPATIAL_SPLIT", na=False).sum()),
                "hotspot_tethered_facilities": int(
                    tags.str.contains("HOTSPOT_TETHERED_FACILITY", na=False).sum()
                ),
                "commuter_device_facilities": int(tags.str.contains("COMMUTER_DEVICE", na=False).sum()),
                "relocated_device_facilities": int(tags.str.contains("RELOCATED_DEVICE", na=False).sum()),
                "coherence_penalised": int((audit_df["p_coherence"] < 1.0).sum()),
                "confidence_high": int((levels == "HIGH").sum()),
                "confidence_medium": int((levels == "MEDIUM").sum()),
                "confidence_low": int((levels == "LOW").sum()),
                "strategy_agreement_pct": round(
                    float(audit_df["strategy_agreement"].eq(True).mean()) * 100.0, 1
                ),
                "resolved_by_name_match": int((audit_df["anchor_resolved_by"] == RESOLVED_BY_NAME_MATCH).sum()),
                "attribution_consistent": int((attribution == ATTRIBUTION_CONSISTENT).sum()),
                "other_entity_nearby": int((attribution == ATTRIBUTION_OTHER_NEARBY).sum()),
                "attribution_unresolved": int((attribution == ATTRIBUTION_UNRESOLVED).sum()),
                "mean_hardware_health_score": round(float(audit_df["hardware_health_score"].mean()), 1),
            }
        )
        return summary

    # ------------------------------------------------------------------
    # Plots
    # ------------------------------------------------------------------
    def plot_stationary_facility_percentage(self) -> go.Figure:
        """Donut of facilities whose scoring cluster includes a STATIONARY device."""
        summary = self.summarize_national_audit()
        if summary["total_facilities"] == 0:
            raise ValueError("No valid facilities available for national mobility analysis.")

        total = summary["total_facilities"]
        has_stationary = summary["stationary_facilities"]
        fig = go.Figure(
            data=[
                go.Pie(
                    labels=["Stationary device in scoring cluster", "No stationary device"],
                    values=[has_stationary, total - has_stationary],
                    hole=0.5,
                    marker=dict(colors=[MOBILITY_COLORS["STATIONARY"], MOBILITY_COLORS["RELOCATED"]]),
                    textinfo="percent",
                    hovertemplate="<b>%{label}</b><br>Facilities: %{value}<br>Share: %{percent}<extra></extra>",
                )
            ]
        )
        fig.update_layout(
            height=380,
            margin=dict(l=10, r=10, t=10, b=10),
            template="plotly_white",
            legend=dict(orientation="h", yanchor="bottom", y=-0.1, xanchor="center", x=0.5),
        )
        return fig

    def facility_cluster_table(self, school_id_giga: str) -> pd.DataFrame:
        """Observation clusters of one facility, as built for anchor selection."""
        clusters = self.facility_clusters
        if clusters is None or clusters.empty:
            return pd.DataFrame()
        return clusters[clusters["school_id_giga"] == school_id_giga].reset_index(drop=True)

    def facility_event_table(self, school_id_giga: str) -> pd.DataFrame:
        """
        All fix events of one facility. `facility_cluster_id` is set for
        events inside the anchor window and NaN for the rest.
        """
        events = self.spatial_profiler.fix_events
        events = events[events["school_id_giga"] == school_id_giga].copy()
        labelled = self.facility_events
        if labelled is not None and not labelled.empty:
            labelled = labelled.loc[
                labelled["school_id_giga"] == school_id_giga, ["fix_event_id", "facility_cluster_id"]
            ]
            events = events.merge(labelled, on="fix_event_id", how="left")
        else:
            events["facility_cluster_id"] = np.nan
        events["in_anchor_window"] = events["facility_cluster_id"].notna()
        return events

    def _nearest_other_pin(self, res: Dict[str, Any]) -> Optional[pd.Series]:
        other_id = res.get("nearest_other_entity_id")
        if other_id is None or self.entity_pins is None:
            return None
        match = self.entity_pins[self.entity_pins["school_id_giga"] == other_id]
        return None if match.empty else match.iloc[0]

    @staticmethod
    def _circle(lat: float, lon: float, radius_m: float, points: int = 72) -> tuple:
        angles = np.linspace(0, 2 * np.pi, points)
        dlat = (radius_m / 6_371_000.0) * np.cos(angles)
        dlon = (radius_m / 6_371_000.0) * np.sin(angles) / np.cos(np.radians(lat))
        return lat + np.degrees(dlat), lon + np.degrees(dlon)

    def plot_facility_map(self, school_id_giga: str, geofence_radius_m: Optional[float] = None) -> go.Figure:
        """
        Map of the facility's fix events coloured by observation cluster,
        with the anchor, the strategy candidates, the official pin, the
        nearest other entity pin, and an optional geofence circle.
        """
        res = self.evaluate_facility_location_confidence(school_id_giga)
        clusters = self.facility_cluster_table(school_id_giga)
        events = self.facility_event_table(school_id_giga)
        if events.empty:
            raise ValueError(f"Insufficient telemetry data for school: {school_id_giga}")

        fig = go.Figure()
        outside = events[~events["in_anchor_window"]]
        labelled = events[events["in_anchor_window"]]
        if not outside.empty:
            fig.add_trace(
                go.Scattermap(
                    lat=outside["detected_latitude"],
                    lon=outside["detected_longitude"],
                    mode="markers",
                    marker=dict(size=7, color=NOISE_COLOR, opacity=0.5),
                    name="Outside anchor window",
                )
            )
        for cluster_id, group in labelled.groupby("facility_cluster_id"):
            cluster_id = int(cluster_id)
            fig.add_trace(
                go.Scattermap(
                    lat=group["detected_latitude"],
                    lon=group["detected_longitude"],
                    mode="markers",
                    marker=dict(size=9, opacity=0.7),
                    hovertext=[
                        f"Device: {d}<br>BSSID: {b}<br>SSID: {s}<br>Accuracy: {a}m"
                        for d, b, s, a in zip(
                            group["device_id"],
                            group["detected_wifi_bssid"],
                            group["detected_wifi_ssid"],
                            group.get("detected_location_accuracy", pd.Series(np.nan, index=group.index)),
                        )
                    ],
                    hoverinfo="text",
                    name=f"Cluster {cluster_id}",
                )
            )

        has_anchor = pd.notna(res["empirical_latitude"])
        if has_anchor and geofence_radius_m:
            circle_lat, circle_lon = self._circle(
                res["empirical_latitude"], res["empirical_longitude"], float(geofence_radius_m)
            )
            fig.add_trace(
                go.Scattermap(
                    lat=circle_lat,
                    lon=circle_lon,
                    mode="lines",
                    line=dict(color=GEOFENCE_COLOR, width=2),
                    name=f"Geofence ({geofence_radius_m:g} m)",
                    hoverinfo="skip",
                )
            )
        if not clusters.empty:
            candidates = clusters[clusters["is_candidate"] & ~clusters["is_anchor_cluster"]]
            if not candidates.empty:
                fig.add_trace(
                    go.Scattermap(
                        lat=candidates["centroid_lat"],
                        lon=candidates["centroid_lon"],
                        mode="markers+text",
                        marker=dict(size=16, color=CANDIDATE_COLOR),
                        text=[f"Candidate {c}" for c in candidates["facility_cluster_id"]],
                        textposition="top center",
                        name="Other candidates",
                    )
                )
        if has_anchor:
            fig.add_trace(
                go.Scattermap(
                    lat=[res["empirical_latitude"]],
                    lon=[res["empirical_longitude"]],
                    mode="markers+text",
                    marker=dict(size=20, color=ANCHOR_COLOR),
                    text=["Anchor"],
                    textposition="top center",
                    name="Facility anchor",
                )
            )
        if pd.notna(res["govt_latitude"]):
            label = (
                f"Official pin ({res['govt_displacement_m']:,.0f} m)"
                if pd.notna(res["govt_displacement_m"])
                else "Official pin"
            )
            fig.add_trace(
                go.Scattermap(
                    lat=[res["govt_latitude"]],
                    lon=[res["govt_longitude"]],
                    mode="markers+text",
                    marker=dict(size=20, color=GOVT_PIN_COLOR),
                    text=[label],
                    textposition="bottom center",
                    name="Official pin",
                )
            )
        other = self._nearest_other_pin(res)
        if other is not None:
            fig.add_trace(
                go.Scattermap(
                    lat=[other["govt_latitude"]],
                    lon=[other["govt_longitude"]],
                    mode="markers+text",
                    marker=dict(size=16, color=OTHER_ENTITY_COLOR),
                    text=[f"Nearest other entity ({res['nearest_other_entity_distance_m']:,.0f} m)"],
                    textposition="bottom center",
                    hovertext=[f"{other.get('school_name', '')} ({other['school_id_giga']})"],
                    name="Nearest other entity pin",
                )
            )

        center_lat = res["empirical_latitude"] if has_anchor else events["detected_latitude"].median()
        center_lon = res["empirical_longitude"] if has_anchor else events["detected_longitude"].median()
        fig.update_layout(
            map=dict(style="open-street-map", center=dict(lat=center_lat, lon=center_lon), zoom=14),
            height=600,
            margin=dict(l=0, r=0, t=0, b=0),
            legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
        )
        return fig

    def plot_facility_evidence_timeline(self, school_id_giga: str) -> go.Figure:
        """Fix events per local date and observation cluster, one row per cluster."""
        events = self.facility_event_table(school_id_giga)
        if events.empty:
            raise ValueError(f"Insufficient telemetry data for school: {school_id_giga}")
        res = self.evaluate_facility_location_confidence(school_id_giga)
        anchor = res["anchor_cluster_id"]

        def label(cluster_id: Any) -> str:
            if pd.isna(cluster_id):
                return "Outside anchor window"
            cluster_id = int(cluster_id)
            return f"Cluster {cluster_id} (anchor)" if cluster_id == anchor else f"Cluster {cluster_id}"

        events["cluster_label"] = events["facility_cluster_id"].map(label)
        daily = (
            events.groupby(["local_date", "cluster_label"])
            .agg(fix_events=("fix_event_id", "size"), devices=("device_id", "nunique"))
            .reset_index()
        )
        daily["local_date"] = pd.to_datetime(daily["local_date"])
        color_map = {name: NOISE_COLOR for name in daily["cluster_label"] if name == "Outside anchor window"}
        color_map.update({name: ANCHOR_COLOR for name in daily["cluster_label"] if name.endswith("(anchor)")})
        fig = px.scatter(
            daily,
            x="local_date",
            y="cluster_label",
            size="fix_events",
            color="cluster_label",
            color_discrete_map=color_map,
            hover_data=["fix_events", "devices"],
            size_max=14,
            labels={"local_date": "Local date", "cluster_label": "Cluster", "fix_events": "Fix events"},
            height=max(220, 60 * daily["cluster_label"].nunique() + 120),
        )
        fig.update_layout(template="plotly_white", showlegend=False, margin=dict(l=10, r=10, t=10, b=30))
        return fig

    def plot_score_breakdown(self, school_id_giga: str) -> go.Figure:
        """Horizontal bars for the five S_raw components of the scoring cluster."""
        cfg = self.config
        res = self.evaluate_facility_location_confidence(school_id_giga)
        breakdown = res.get("score_breakdown") or {}
        categories = ["Stability", "Consensus", "BSSID Depth", "Temporal Depth", "API Precision"]
        keys = ["stability", "consensus", "bssid", "depth", "precision"]
        scores = [breakdown.get(k, 0.0) for k in keys]
        max_scores = [
            cfg.stability_points[0],
            cfg.consensus_max,
            cfg.bssid_points[0],
            cfg.depth_max,
            cfg.precision_max,
        ]

        fig = go.Figure(
            go.Bar(
                y=categories,
                x=scores,
                orientation="h",
                marker=dict(color=ANCHOR_COLOR),
                text=[f"{s:g}/{m:g} pts" for s, m in zip(scores, max_scores)],
                textposition="auto",
            )
        )
        fig.update_layout(
            xaxis=dict(title="Points", range=[0, max(max_scores) + 5]),
            yaxis=dict(autorange="reversed"),
            height=300,
            margin=dict(l=10, r=10, t=10, b=30),
            template="plotly_white",
        )
        return fig

    def plot_location_triage(self) -> go.Figure:
        """
        Anchor distance to the official pin (log scale) against the Track 1
        confidence score, coloured by recommended action. Vertical lines are
        the distance bands, horizontal lines the confidence tiers.
        """
        audit_df = self.run_national_facility_audit()
        plotted = audit_df[audit_df["govt_displacement_m"].notna()].copy() if not audit_df.empty else audit_df
        if plotted.empty:
            fig = go.Figure()
            fig.update_layout(title="No facilities with both an anchor and an official pin")
            return fig

        plotted["distance_plot_m"] = plotted["govt_displacement_m"].clip(lower=1.0)
        cfg = self.config
        fig = px.scatter(
            plotted,
            x="distance_plot_m",
            y="location_confidence_score",
            color="recommended_action",
            color_discrete_map=ACTION_COLORS,
            category_orders={"recommended_action": ACTION_ORDER},
            log_x=True,
            hover_name="school_name",
            hover_data={
                "school_id_giga": True,
                "location_verification_flag": True,
                "govt_displacement_m": ":,.0f",
                "location_confidence_level": True,
                "distinct_devices": True,
                "distance_plot_m": False,
            },
            labels={
                "distance_plot_m": "Anchor distance to official pin (m, log scale)",
                "location_confidence_score": "Location confidence score",
                "recommended_action": "Action",
                "location_verification_flag": "Flag",
            },
            height=440,
        )
        for x, name in ((cfg.verified_max_m, "verified"), (cfg.mismatch_min_m, "mismatch")):
            add_log_x_vline(fig, x, f"{name} ({x:g} m)")
        for y, name in ((cfg.confidence_high_min, "HIGH"), (cfg.confidence_medium_min, "MEDIUM")):
            fig.add_hline(y=y, line_dash="dot", line_color="gray", annotation_text=f"{name} ({y:g})")
        fig.update_traces(marker=dict(size=8, opacity=0.8))
        fig.update_layout(
            yaxis=dict(range=[0, 105]),
            template="plotly_white",
            margin=dict(l=10, r=10, t=30, b=30),
            legend=dict(orientation="h", yanchor="top", y=-0.18, xanchor="left", x=0, title_text=""),
        )
        return fig

    def plot_flag_confidence_breakdown(self) -> go.Figure:
        """Facility counts per Track 1 flag, stacked by confidence tier."""
        audit_df = self.run_national_facility_audit()
        if audit_df.empty:
            fig = go.Figure()
            fig.update_layout(title="No national audit data available")
            return fig

        counts = (
            audit_df.groupby(["location_verification_flag", "location_confidence_level"])
            .size()
            .reset_index(name="facilities")
        )
        counts["flag"] = counts["location_verification_flag"].str.replace("_", " ").str.capitalize()
        flag_order = [f.replace("_", " ").capitalize() for f in FLAG_ORDER]
        fig = px.bar(
            counts,
            y="flag",
            x="facilities",
            color="location_confidence_level",
            orientation="h",
            color_discrete_map=CONFIDENCE_COLORS,
            category_orders={"flag": flag_order, "location_confidence_level": CONFIDENCE_ORDER},
            labels={"flag": "", "facilities": "Facilities", "location_confidence_level": "Confidence"},
            height=440,
        )
        fig.update_layout(
            template="plotly_white",
            yaxis=dict(automargin=True),
            margin=dict(l=10, r=10, t=10, b=30),
            legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="left", x=0),
        )
        return fig
