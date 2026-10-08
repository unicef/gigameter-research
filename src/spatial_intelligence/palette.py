"""
Module: src/spatial_intelligence/palette.py
Purpose: One colour per methodology category, shared by every plot and the
         dashboard, so a flag or class looks the same everywhere.
"""

FLAG_COLORS = {
    "VERIFIED_ACCURATE": "#2e7d32",
    "CAMPUS_DISPERSION": "#f9a825",
    "GOVT_PIN_MISMATCH": "#c62828",
    "AMBIGUOUS_MULTI_CLUSTER": "#6a1b9a",
    "UNSTABLE_MOBILE_ONLY": "#ef6c00",
    "NO_GOVT_PIN_AVAILABLE": "#546e7a",
    "INSUFFICIENT_DATA": "#9e9e9e",
}

ACTION_COLORS = {
    "SUBMIT_CORRECTION": "#c62828",
    "FIELD_VERIFY": "#ef6c00",
    "AWAIT_DATA": "#9e9e9e",
    "NONE": "#2e7d32",
}

CONFIDENCE_COLORS = {"HIGH": "#2e7d32", "MEDIUM": "#f9a825", "LOW": "#c62828"}

MOBILITY_COLORS = {
    "STATIONARY": "#2e7d32",
    "COMMUTER": "#1565c0",
    "RELOCATED": "#ef6c00",
    "HIGH_MOBILITY": "#c62828",
    "INSUFFICIENT_EVIDENCE": "#9e9e9e",
}

ATTRIBUTION_COLORS = {
    "CONSISTENT": "#2e7d32",
    "OTHER_ENTITY_NEARBY": "#c62828",
    "UNRESOLVED": "#9e9e9e",
}

ANCHOR_COLOR = "#2e7d32"
CANDIDATE_COLOR = "#ef6c00"
GOVT_PIN_COLOR = "#c62828"
OTHER_ENTITY_COLOR = "#6a1b9a"
NOISE_COLOR = "#9e9e9e"
GEOFENCE_COLOR = "#f9a825"

FLAG_ORDER = list(FLAG_COLORS)
ACTION_ORDER = list(ACTION_COLORS)
CONFIDENCE_ORDER = list(CONFIDENCE_COLORS)
MOBILITY_ORDER = list(MOBILITY_COLORS)
