"""
Module: src/spatial_intelligence/config.py
Purpose: Versioned settings for the spatial methodology.
Rules: Defaults follow the methodology Parameters page. Every output that
       depends on these settings carries `methodology_version` and
       `config_hash`.
"""

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any, Tuple

STRATEGY_GOVT_PROXIMITY = "govt_proximity_anchor"
STRATEGY_TELEMETRY_DOMINANCE = "telemetry_dominance"
STRATEGY_STATIONARY_FIRST = "stationary_first"
KNOWN_STRATEGIES = (
    STRATEGY_GOVT_PROXIMITY,
    STRATEGY_TELEMETRY_DOMINANCE,
    STRATEGY_STATIONARY_FIRST,
)

DEFAULT_HOTSPOT_SSID_PATTERN = (
    r"(?i)(?:iphone|android|galaxy|hotspot|teacher|pixel|redmi|tether|"
    r"samsung|huawei|oppo|vivo|xiaomi|realme|mobicom|unitel|mifi)"
)

DEFAULT_NAME_MATCH_GENERIC_TOKENS = (
    "shkolla",
    "shkolle",
    "vjecare",
    "bashkuar",
    "mesme",
    "fillore",
    "kopshti",
    "school",
    "primary",
    "secondary",
    "high",
    "escuela",
    "ecole",
    "wifi",
    "guest",
    "ext",
    "the",
    "of",
    "e",
    "i",
    "2g",
    "4g",
    "5g",
)


@dataclass(frozen=True)
class SpatialConfig:
    """
    Settings shared by the mobility, profiling, and validation modules.

    Distances are meters, durations are seconds, and score values are points.
    `operational_hours` is an inclusive pair of local hours, so `(8, 19)`
    covers 08:00:00 to 19:59:59. `workdays` uses pandas weekday numbers,
    Monday = 0.

    Raises:
        ValueError: From `__post_init__` when settings contradict each other.
    """

    methodology_version: str = "0.3"

    # Evidence and time window
    operational_hours: Tuple[int, int] = (8, 19)
    workdays: Tuple[int, ...] = (0, 1, 2, 3, 4)
    burst_window_s: float = 300.0
    accuracy_floor_m: float = 1.0
    min_support_device_days: int = 2

    # Hotspot and BSSID mobility
    hotspot_ssid_pattern: str = DEFAULT_HOTSPOT_SSID_PATTERN
    bssid_mobility_accuracy_gate_m: float = 200.0
    bssid_mobility_eps_m: float = 250.0
    bssid_mobility_min_samples: int = 2
    bssid_mobility_min_cluster_days: int = 2

    # Device mobility
    device_eps_m: float = 150.0
    device_min_samples: int = 3
    min_cluster_device_days: int = 2
    max_noise_share: float = 0.25
    commuter_min_alternations: int = 2
    geofence_radius_m: float = 200.0

    # Facility anchor
    anchor_eps_m: float = 150.0
    govt_anchor_radius_m: float = 2000.0
    strategies: Tuple[str, ...] = (
        STRATEGY_GOVT_PROXIMITY,
        STRATEGY_TELEMETRY_DOMINANCE,
    )
    name_match_generic_tokens: Tuple[str, ...] = DEFAULT_NAME_MATCH_GENERIC_TOKENS

    # Raw score
    stability_points: Tuple[float, float, float] = (30.0, 20.0, 10.0)
    consensus_max: float = 25.0
    consensus_single_device: float = 12.5
    consensus_full_m: float = 30.0
    consensus_zero_m: float = 200.0
    bssid_points: Tuple[float, float] = (20.0, 10.0)
    bssid_full_days: int = 3
    depth_max: float = 15.0
    depth_full_device_days: int = 10
    precision_max: float = 10.0
    precision_full_m: float = 10.0
    precision_zero_m: float = 100.0

    # Track 1
    verified_max_m: float = 200.0
    mismatch_min_m: float = 500.0
    confidence_high_min: float = 70.0
    confidence_medium_min: float = 50.0

    # Track 2
    coherence_full_m: float = 1000.0
    split_m: float = 2000.0
    coherence_floor: float = 0.1
    hotspot_share_min: float = 0.5

    # Track 3
    other_entity_radius_m: float = 200.0

    def __post_init__(self) -> None:
        errors = []
        start_hour, end_hour = self.operational_hours
        if not 0 <= start_hour <= end_hour <= 23:
            errors.append("operational_hours must satisfy 0 <= start <= end <= 23")
        if not self.workdays or any(day not in range(7) for day in self.workdays):
            errors.append("workdays must be a non-empty subset of 0..6")
        if self.device_min_samples < 2:
            errors.append("device_min_samples must be >= 2")
        if self.bssid_mobility_min_samples < 2:
            errors.append("bssid_mobility_min_samples must be >= 2")
        if not 0.0 <= self.max_noise_share < 1.0:
            errors.append("max_noise_share must be in [0, 1)")
        if not 0.0 < self.hotspot_share_min <= 1.0:
            errors.append("hotspot_share_min must be in (0, 1]")
        if self.verified_max_m >= self.mismatch_min_m:
            errors.append("verified_max_m must be < mismatch_min_m")
        if self.coherence_full_m >= self.split_m:
            errors.append("coherence_full_m must be < split_m")
        if self.consensus_full_m >= self.consensus_zero_m:
            errors.append("consensus_full_m must be < consensus_zero_m")
        if self.precision_full_m >= self.precision_zero_m:
            errors.append("precision_full_m must be < precision_zero_m")
        if self.confidence_medium_min >= self.confidence_high_min:
            errors.append("confidence_medium_min must be < confidence_high_min")
        if not 0.0 < self.coherence_floor <= 1.0:
            errors.append("coherence_floor must be in (0, 1]")
        unknown = [s for s in self.strategies if s not in KNOWN_STRATEGIES]
        if unknown or not self.strategies:
            errors.append(
                "strategies must be a non-empty subset of " + ", ".join(KNOWN_STRATEGIES)
            )
        if errors:
            raise ValueError("Invalid SpatialConfig: " + "; ".join(errors))

    def to_dict(self) -> dict:
        """Return the settings as plain JSON-serialisable values."""
        return json.loads(json.dumps(asdict(self)))

    @property
    def config_hash(self) -> str:
        """Short, stable hash of every setting, for reproducibility stamps."""
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]

    def provenance(self) -> dict:
        """Fields stamped onto every methodology output row."""
        return {
            "methodology_version": self.methodology_version,
            "config_hash": self.config_hash,
        }

    def with_overrides(self, **changes: Any) -> "SpatialConfig":
        """Return a validated copy with `changes` applied."""
        return replace(self, **changes)


DEFAULT_CONFIG = SpatialConfig()
