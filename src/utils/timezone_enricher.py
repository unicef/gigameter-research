"""
Module: src/utils/timezone_enricher.py
Purpose: Spatial timezone resolution and local time feature engineering
         for GigaMeter telemetry datasets (Pillars 1-5).
Rules: GigaMeter Technical Specs v2.2 - Active Operational Hours (08:00 - 19:59 local time).
"""

import pandas as pd
import numpy as np
from timezonefinder import TimezoneFinder
import pytz
import pycountry

# Initialize TimezoneFinder once to reuse polygon spatial index in memory
_tf = TimezoneFinder()


def _resolve_single_school_tz(row: pd.Series) -> str:
    """
    Cascading resolution helper for a single school facility row:
    1. Official government pins (`govt_latitude` / `govt_longitude`)
    2. Empirical Wi-Fi Lat/Lon (`detected_latitude` / `detected_longitude`)
    3. Country ISO3 Alpha-3 Fallback
    4. UTC
    """
    # Tier 1: Official school coordinates already merged onto the frame
    latitude, longitude = row.get("govt_latitude"), row.get("govt_longitude")
    if pd.notna(latitude) and pd.notna(longitude):
        try:
            tz = _tf.timezone_at(lat=float(latitude), lng=float(longitude))
            if tz:
                return tz
        except ValueError:
            pass  # Handle out-of-bounds coordinates

    # Tier 2: Empirical Wi-Fi Resolved Coordinates (Google API)
    det_lat, det_lon = row.get("detected_latitude"), row.get("detected_longitude")
    if pd.notna(det_lat) and pd.notna(det_lon):
        try:
            tz = _tf.timezone_at(lat=float(det_lat), lng=float(det_lon))
            if tz:
                return tz
        except ValueError:
            pass

    # Tier 3: ISO3 Country Code Lookup (pycountry -> pytz)
    iso3 = row.get("iso3_code")
    if pd.notna(iso3):
        try:
            country_obj = pycountry.countries.get(alpha_3=str(iso3).strip().upper())
            if country_obj and hasattr(country_obj, "alpha_2"):
                country_tzs = pytz.country_timezones.get(country_obj.alpha_2)
                if country_tzs:
                    return country_tzs[0]  # Return primary national timezone
        except Exception:
            pass

    # Tier 4: Baseline Fallback
    return "UTC"


def build_school_timezone_map(telemetry_df: pd.DataFrame) -> dict:
    """
    Construct a dictionary mapping `school_id_giga` to an IANA timezone string.

    The frame must already use canonical identifiers and, when official pins
    are available, `govt_latitude` / `govt_longitude`. Facilities are
    deduplicated first so spatial lookup is O(N_schools) rather than O(N_rows).

    Args:
        telemetry_df: Canonical telemetry, with school pins already merged.

    Returns:
        Mapping of `school_id_giga` to an IANA timezone name.

    Raises:
        ValueError: If `school_id_giga` is missing.
    """
    df = telemetry_df.copy()
    if "school_id_giga" not in df.columns:
        raise ValueError("Telemetry frame is missing required column: school_id_giga")

    for col in [
        "detected_latitude",
        "detected_longitude",
        "govt_latitude",
        "govt_longitude",
        "iso3_code",
    ]:
        if col not in df.columns:
            df[col] = np.nan

    unique_facilities = df[
        [
            "school_id_giga",
            "govt_latitude",
            "govt_longitude",
            "detected_latitude",
            "detected_longitude",
            "iso3_code",
        ]
    ].drop_duplicates(subset=["school_id_giga"])

    print(f"Resolving timezones for {len(unique_facilities):,} unique facilities...")

    tz_map = {}
    for _, row in unique_facilities.iterrows():
        school_id = row["school_id_giga"]
        tz_map[school_id] = _resolve_single_school_tz(row)

    return tz_map


def enrich_telemetry_with_local_time(
    telemetry_df: pd.DataFrame,
    timestamp_col: str = "created_timestamp",
) -> pd.DataFrame:
    """
    Convert UTC telemetry timestamps into local device time.

    Official school coordinates must already be on the frame as
    `govt_latitude` and `govt_longitude`. This function maps each
    `school_id_giga` to an IANA timezone, converts `timestamp_col` from UTC,
    and sets the GigaMeter operational window (08:00-19:59 local time).

    Args:
        telemetry_df: Canonical telemetry frame.
        timestamp_col: UTC timestamp column to convert.

    Returns:
        A copy of `telemetry_df` with `tz_name`, `created_timestamp_utc`,
        `local_created_timestamp`, `local_date`, `local_hour`,
        `local_day_of_week`, `is_weekday`, and `is_operational_hours`.

    Raises:
        ValueError: If `school_id_giga` is missing.
    """
    df = telemetry_df.copy()
    if "school_id_giga" not in df.columns:
        raise ValueError("Telemetry frame is missing required column: school_id_giga")

    tz_map = build_school_timezone_map(df)
    df["tz_name"] = df["school_id_giga"].map(tz_map).fillna("UTC")

    # Step 3: Parse UTC timestamp
    df["created_timestamp_utc"] = pd.to_datetime(
        df[timestamp_col], format="ISO8601", utc=True
    )

    # Step 4: Convert to local time grouped by timezone for vectorized performance
    def _convert_group(group: pd.DataFrame) -> pd.DataFrame:
        tz_str = group.name
        try:
            group["local_created_timestamp"] = (
                group["created_timestamp_utc"]
                .dt.tz_convert(tz_str)
                .dt.tz_localize(
                    None
                )  # Remove timezone offset for standard local arithmetic
            )
        except Exception:
            group["local_created_timestamp"] = group[
                "created_timestamp_utc"
            ].dt.tz_localize(None)
        return group

    print("Converting UTC timestamps to local device time...")
    df = df.groupby("tz_name", group_keys=False).apply(_convert_group)

    # Step 5: Derive Local Calendar & Operational Hours Features (Section 2.1 & 2.3)
    df["local_date"] = df["local_created_timestamp"].dt.date
    df["local_hour"] = df["local_created_timestamp"].dt.hour
    df["local_day_of_week"] = df["local_created_timestamp"].dt.day_name()
    df["is_weekday"] = df["local_created_timestamp"].dt.dayofweek < 5

    # GigaMeter Operational Window: Strictly 08:00:00 to 19:59:59 local device time (hours 8 through 19)
    df["is_operational_hours"] = df["local_hour"].between(8, 19)

    return df
