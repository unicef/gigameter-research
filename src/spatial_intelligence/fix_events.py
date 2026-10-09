"""
Module: src/spatial_intelligence/fix_events.py
Purpose: Convert telemetry rows into fix events, the evidence unit of the
         spatial methodology.

A *fix* is one `(detected_latitude, detected_longitude,
detected_location_accuracy)` triple. Per device and in time order:

* A *run* is a sequence of consecutive rows sharing the same fix. The run's
  *origin network* is the first associated BSSID that appears in it.
* A row is *carried* when it has a BSSID that differs from its run's origin
  network: the coordinates were produced under another network and say
  nothing about this one. Rows without an associated network (wired or
  unassociated) are never carried and do not set the origin, because a
  device switching between cable and Wi-Fi in one place legitimately gets
  the same answer.
* A *fix event* groups consecutive rows of one run and one network that are
  no more than `burst_window_s` apart. A longer gap under the same network
  starts a new event, because a fresh lookup that returns the same answer is
  new evidence.
"""

from typing import Optional

import numpy as np
import pandas as pd

from .config import DEFAULT_CONFIG, SpatialConfig

FIX_COLUMNS = (
    "detected_latitude",
    "detected_longitude",
    "detected_location_accuracy",
)
_NO_NETWORK = "<no-bssid>"


def _network_key(frame: pd.DataFrame) -> pd.Series:
    if "detected_wifi_bssid" not in frame.columns:
        return pd.Series(_NO_NETWORK, index=frame.index, dtype=object)
    bssid = frame["detected_wifi_bssid"].astype(object)
    return bssid.where(bssid.notna(), _NO_NETWORK)


def _fix_changed(frame: pd.DataFrame) -> np.ndarray:
    """True where a row's fix differs from the previous row's fix."""
    changed = np.zeros(len(frame), dtype=bool)
    for column in FIX_COLUMNS:
        if column not in frame.columns:
            continue
        values = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float)
        previous = np.roll(values, 1)
        same = (values == previous) | (np.isnan(values) & np.isnan(previous))
        changed |= ~same
    if len(changed):
        changed[0] = True
    return changed


def mark_fix_events(
    telemetry_df: pd.DataFrame, config: SpatialConfig = DEFAULT_CONFIG
) -> pd.DataFrame:
    """
    Add fix-event columns to telemetry rows with valid coordinates.

    Rows with null `detected_latitude` or `detected_longitude` are dropped;
    no coordinate is imputed. Rows are ordered by `device_id` and UTC
    `created_timestamp`.

    Args:
        telemetry_df: Canonical telemetry from `TelemetryLoader`.
        config: Methodology settings; uses `burst_window_s` and `workdays`.

    Returns:
        A copy with `created_timestamp_utc`, `fix_run_id`,
        `fix_origin_bssid`, `fix_carried`, `fix_event_id` (unique across
        devices), and `is_workday`.
    """
    frame = telemetry_df[
        telemetry_df["detected_latitude"].notna()
        & telemetry_df["detected_longitude"].notna()
    ].copy()
    if frame.empty:
        for column in ("fix_run_id", "fix_event_id"):
            frame[column] = pd.Series(dtype="int64")
        frame["fix_origin_bssid"] = pd.Series(dtype="string")
        frame["fix_carried"] = pd.Series(dtype=bool)
        frame["is_workday"] = pd.Series(dtype=bool)
        frame["created_timestamp_utc"] = pd.Series(dtype="datetime64[ns, UTC]")
        return frame

    frame["_utc"] = pd.to_datetime(frame["created_timestamp"], format="ISO8601", utc=True)
    frame = frame.sort_values(["device_id", "_utc"], kind="mergesort")

    network = _network_key(frame).to_numpy()
    device = frame["device_id"].astype(object).to_numpy()

    new_device = np.ones(len(frame), dtype=bool)
    new_device[1:] = device[1:] != device[:-1]
    new_run = new_device | _fix_changed(frame)
    run_id = pd.Series(np.cumsum(new_run), index=frame.index)

    has_network = network != _NO_NETWORK
    associated = pd.Series(np.where(has_network, network, None), index=frame.index, dtype=object)
    origin = associated.groupby(run_id).transform("first")
    carried = has_network & origin.notna().to_numpy() & (
        associated.to_numpy() != origin.to_numpy()
    )

    network_changed = np.ones(len(frame), dtype=bool)
    network_changed[1:] = network[1:] != network[:-1]
    gap_s = frame["_utc"].diff().dt.total_seconds().to_numpy()
    new_event = new_run | network_changed | (np.nan_to_num(gap_s) > config.burst_window_s)

    frame["fix_run_id"] = run_id.astype("int64")
    frame["fix_origin_bssid"] = origin
    frame["fix_carried"] = carried
    frame["fix_event_id"] = np.cumsum(new_event).astype("int64")

    if "local_created_timestamp" in frame.columns:
        weekday = pd.to_datetime(frame["local_created_timestamp"]).dt.dayofweek
        frame["is_workday"] = weekday.isin(config.workdays)
    else:
        frame["is_workday"] = True

    return frame.drop(columns=["created_timestamp_utc"], errors="ignore").rename(
        columns={"_utc": "created_timestamp_utc"}
    )


def _first_valid(series: pd.Series):
    valid = series.dropna()
    return valid.iloc[0] if not valid.empty else None


def build_fix_event_table(
    telemetry_df: pd.DataFrame,
    config: SpatialConfig = DEFAULT_CONFIG,
    *,
    include_carried: bool = False,
    marked: Optional[bool] = None,
) -> pd.DataFrame:
    """
    Aggregate telemetry rows into one row per fix event.

    Args:
        telemetry_df: Canonical telemetry, or the output of `mark_fix_events`.
        config: Methodology settings.
        include_carried: Keep carried events. They are excluded by default
            because their coordinates belong to another network.
        marked: Whether `telemetry_df` already has fix-event columns.
            Detected from the columns when omitted.

    Returns:
        One row per event with `fix_event_id`, `device_id`, `school_id_giga`,
        coordinates, accuracy, BSSID, SSID, first and last UTC timestamps,
        `local_date`, `local_hour`, `is_operational_hours`, `is_workday`,
        `row_count`, `fix_carried`, and `is_mobile_hotspot` /
        `is_hotspot_ssid` when those row flags exist.
    """
    if marked is None:
        marked = "fix_event_id" in telemetry_df.columns
    rows = telemetry_df if marked else mark_fix_events(telemetry_df, config)
    if not include_carried:
        rows = rows[~rows["fix_carried"]]
    if rows.empty:
        return pd.DataFrame(
            columns=[
                "fix_event_id",
                "device_id",
                "school_id_giga",
                "detected_latitude",
                "detected_longitude",
                "detected_location_accuracy",
                "detected_wifi_bssid",
                "detected_wifi_ssid",
                "first_seen_utc",
                "last_seen_utc",
                "local_date",
                "local_hour",
                "is_operational_hours",
                "is_workday",
                "row_count",
                "fix_carried",
            ]
        )

    agg = {
        "device_id": ("device_id", "first"),
        "school_id_giga": ("school_id_giga", "first"),
        "detected_latitude": ("detected_latitude", "first"),
        "detected_longitude": ("detected_longitude", "first"),
        "first_seen_utc": ("created_timestamp_utc", "min"),
        "last_seen_utc": ("created_timestamp_utc", "max"),
        "row_count": ("device_id", "size"),
        "fix_carried": ("fix_carried", "first"),
        "is_workday": ("is_workday", "first"),
    }
    optional_first = {
        "detected_location_accuracy": "first",
        "local_date": "first",
        "local_hour": "first",
        "local_created_timestamp": "first",
        "is_operational_hours": "first",
        "govt_latitude": "first",
        "govt_longitude": "first",
        "school_name": "first",
    }
    for column, how in optional_first.items():
        if column in rows.columns:
            agg[column] = (column, how)
    for column in ("is_mobile_hotspot", "is_hotspot_ssid", "is_mobile_bssid"):
        if column in rows.columns:
            agg[column] = (column, "any")

    events = rows.groupby("fix_event_id", sort=True).agg(**agg)

    for column in ("detected_wifi_bssid", "detected_wifi_ssid"):
        if column in rows.columns:
            events[column] = rows.groupby("fix_event_id")[column].agg(_first_valid)
        else:
            events[column] = None

    return events.reset_index()
