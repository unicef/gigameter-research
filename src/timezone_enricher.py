"""
Module: src/timezone_enricher.py
Purpose: Spatial timezone resolution and local time feature engineering
         for GigaMeter telemetry datasets (Pillars 1-5).
Rules: GigaMeter Technical Specs v2.2 - Active Operational Hours (08:00 - 19:59 local time).
"""

import pandas as pd
import numpy as np
from timezonefinder import TimezoneFinder
import pytz
import pycountry
from typing import Optional

# Initialize TimezoneFinder once to reuse polygon spatial index in memory
_tf = TimezoneFinder()


def _resolve_single_school_tz(row: pd.Series) -> str:
    """
    Cascading resolution helper for a single school facility row:
    1. Official Latitude/Longitude (Delta Share `schools` table)
    2. Empirical Wi-Fi Lat/Lon (`detected_latitude` / `detected_longitude`)
    3. Country ISO3 Alpha-3 Fallback
    4. UTC
    """
    # Tier 1: Official Static School Coordinates from Delta Share
    latitude, longitude = row.get("latitude"), row.get("longitude")
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


def build_school_timezone_map(
    telemetry_df: pd.DataFrame, schools_df: Optional[pd.DataFrame] = None
) -> dict:
    """
    Constructs a dictionary mapping `giga_id_school` -> IANA Timezone string.
    Deduplicates facilities first to optimize spatial lookup speed from O(N_rows) to O(N_schools).
    """
    # Standardize identifier anchoring (Section 1)
    df = telemetry_df.copy()

    if "giga_id_school" in df:
        df = df.rename(columns={"giga_id_school": "school_id_giga"})

    # Merge Delta Share school coordinates if provided
    if schools_df is not None and not schools_df.empty:
        df = df.merge(
            schools_df[["school_id_giga", "latitude", "longitude"]],
            on="school_id_giga",
            how="left",
        )

    # Ensure required columns exist
    for col in [
        "detected_latitude",
        "detected_longitude",
        "latitude",
        "longitude",
        "iso3_code",
    ]:
        if col not in df.columns:
            df[col] = np.nan

    # Deduplicate by school ID to minimize spatial calculations
    unique_facilities = df[
        [
            "school_id_giga",
            "latitude",
            "longitude",
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
    schools_df: Optional[pd.DataFrame] = None,
    timestamp_col: str = "created_timestamp",
) -> pd.DataFrame:
    """
    Main Pipeline Function:
    1. Merges official school coordinates (`latitude`, `longitude`).
    2. Builds spatial timezone mapping (`tz_name`).
    3. Converts UTC timestamps to device local time.
    4. Computes GigaMeter Active Operational Window (08:00 - 19:59 local device time).
    """
    df = telemetry_df.copy()

    if "giga_id_school" in df:
        df = df.rename(columns={"giga_id_school": "school_id_giga"})

    # Step 1: Merge official school coordinates if provided
    if schools_df is not None and not schools_df.empty:
        # Avoid duplicate coordinate columns on merge
        cols_to_drop = [c for c in ["latitude", "longitude"] if c in df.columns]
        if cols_to_drop:
            df = df.drop(columns=cols_to_drop)

        df = df.merge(
            schools_df[["school_id_giga", "latitude", "longitude"]],
            on="school_id_giga",
            how="left",
        )

    # Step 2: Build & Map Timezone
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
