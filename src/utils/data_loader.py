"""
Module: src/utils/data_loader.py
Purpose: Single ingestion path for GigaMeter spatial telemetry.
         Canonicalizes column names, merges official school coordinates,
         and enriches UTC timestamps to local device time.
"""

from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Union

import pandas as pd

from src.utils.timezone_enricher import enrich_telemetry_with_local_time

TELEMETRY_COLUMN_ALIASES: Dict[str, str] = {
    "giga_id_school": "school_id_giga",
    "device_hardware_id": "device_id",
    "detected_bssid": "detected_wifi_bssid",
    "detected_ssid": "detected_wifi_ssid",
    "detected_wifi_signal": "wifi_signal_dbm",
}

REQUIRED_TELEMETRY_COLUMNS = (
    "school_id_giga",
    "device_id",
    "detected_latitude",
    "detected_longitude",
    "created_timestamp",
)

LOCAL_TIME_COLUMNS = (
    "tz_name",
    "local_created_timestamp",
    "local_date",
    "local_hour",
    "local_day_of_week",
    "is_weekday",
    "is_operational_hours",
)

_LOCAL_TIME_SKIP_COLUMNS = (
    "local_created_timestamp",
    "local_hour",
    "is_operational_hours",
)


def canonicalize_telemetry_columns(telemetry_df: pd.DataFrame) -> pd.DataFrame:
    """
    Rename known telemetry synonyms to the canonical column contract.

    `is_school_hours` is renamed to `is_operational_hours` only when the
    canonical flag is absent. Official `latitude` / `longitude` pins already
    merged onto a frame are renamed to `govt_latitude` / `govt_longitude`
    only when those govt columns are absent. The input frame is not modified.

    Args:
        telemetry_df: Telemetry measurements from SQL, a file, or a caller.

    Returns:
        A copy of `telemetry_df` using canonical column names.
    """
    frame = telemetry_df.copy()
    rename: Dict[str, str] = {
        source: target
        for source, target in TELEMETRY_COLUMN_ALIASES.items()
        if source in frame.columns and target not in frame.columns
    }
    if (
        "is_operational_hours" not in frame.columns
        and "is_school_hours" in frame.columns
    ):
        rename["is_school_hours"] = "is_operational_hours"
    if "govt_latitude" not in frame.columns and "latitude" in frame.columns:
        rename["latitude"] = "govt_latitude"
    if "govt_longitude" not in frame.columns and "longitude" in frame.columns:
        rename["longitude"] = "govt_longitude"
    if rename:
        frame = frame.rename(columns=rename)
    return frame


def prepare_schools_frame(schools_df: pd.DataFrame) -> pd.DataFrame:
    """
    Reduce a schools table to the join key and official coordinates.

    The schools table, whether supplied by the caller or loaded from Delta
    Sharing, must contain `latitude` and `longitude`. Those columns are
    renamed to `govt_latitude` and `govt_longitude`. `giga_id_school` is
    renamed to `school_id_giga` when that is the identifier column.

    Args:
        schools_df: Official school metadata, one row per facility.

    Returns:
        Deduplicated columns `school_id_giga`, `govt_latitude`, and
        `govt_longitude`.

    Raises:
        ValueError: If the identifier or coordinate columns are missing.
    """
    missing = [
        column
        for column in ("latitude", "longitude")
        if column not in schools_df.columns
    ]
    if missing:
        raise ValueError(
            "Schools frame is missing required columns: " + ", ".join(missing)
        )

    frame = schools_df.copy()
    if "giga_id_school" in frame.columns and "school_id_giga" not in frame.columns:
        frame = frame.rename(columns={"giga_id_school": "school_id_giga"})
    if "school_id_giga" not in frame.columns:
        raise ValueError("Schools frame is missing required column: school_id_giga")

    frame = frame.rename(
        columns={"latitude": "govt_latitude", "longitude": "govt_longitude"}
    )
    return frame[
        ["school_id_giga", "govt_latitude", "govt_longitude"]
    ].drop_duplicates(subset=["school_id_giga"])


def _require_columns(frame: pd.DataFrame, columns: tuple) -> None:
    """Raise ValueError listing any required columns that are absent."""
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(
            "Telemetry frame is missing required columns: " + ", ".join(missing)
        )


def _resolve_country_iso3(
    country_iso3: Optional[str], query_params: Optional[Mapping[str, Any]]
) -> Optional[str]:
    """Prefer an explicit country code, then the SQL template parameter."""
    if country_iso3:
        return country_iso3
    if query_params and query_params.get("country_iso3"):
        return str(query_params["country_iso3"])
    return None


def _checked_db_connection(db: Any) -> Any:
    """
    Return a database client that has passed `test_connection()`.

    When `db` is omitted, construct `DBConnection` with no arguments so it
    reads credentials from `.env`.
    """
    if db is None:
        from gigaspatial.core.io import DBConnection

        db = DBConnection()
    if not db.test_connection():
        raise ConnectionError(
            "Database connection test failed. Check database credentials in .env."
        )
    return db


def _delta_store_or_default(delta_store: Any) -> Any:
    """
    Return the provided Delta Sharing client, or a zero-argument default.

    `DeltaSharingDataStore` reads credentials from `.env` and raises on its
    own when the profile, share, or table is wrong.
    """
    if delta_store is not None:
        return delta_store
    from gigaspatial.core.io import DeltaSharingDataStore

    return DeltaSharingDataStore()


class TelemetryLoader:
    """
    Load spatial telemetry into the canonical analysis frame.

    Provide exactly one source: `telemetry_df`, `file_path`, or `query_name`
    with `query_params`. A `.csv` or `.parquet` file is read from `file_path`.
    `query_name` is a template stem under `sql/` formatted with `query_params`.

    When `govt_latitude` is already on the frame, school coordinates and both
    clients are skipped. Otherwise pins are merged from `schools_df`, or from
    `delta_store.load_table(country_iso3)` when `schools_df` is omitted.
    Local-time enrichment is skipped when `local_created_timestamp`,
    `local_hour`, and `is_operational_hours` are already present.
    """

    def __init__(self, sql_dir: Optional[Union[str, Path]] = None) -> None:
        """
        Args:
            sql_dir: Directory of `.sql` templates. Defaults to the repository
                `sql/` directory.
        """
        if sql_dir is None:
            self.sql_dir = Path(__file__).resolve().parents[2] / "sql"
        else:
            self.sql_dir = Path(sql_dir)

    def load(
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
    ) -> pd.DataFrame:
        """
        Load, canonicalize, pin-merge, and locally time-enrich telemetry.

        Args:
            telemetry_df: In-memory measurements. Mutually exclusive with
                `file_path` and `query_name`.
            file_path: `.csv` or `.parquet` ledger path.
            query_name: SQL template stem, without the `.sql` suffix.
            query_params: Values for the SQL template placeholders.
            country_iso3: ISO3 code passed to `delta_store.load_table`.
                Defaults to `query_params["country_iso3"]` when omitted.
            schools_df: Official school metadata. Used only when the telemetry
                frame does not already contain `govt_latitude`.
            timestamp_col: UTC timestamp column read by the timezone enricher.
            db: Database client with `test_connection` and
                `read_sql_to_dataframe`. Constructed with `DBConnection()`
                when a query is requested and this is omitted.
            delta_store: Delta Sharing client with `load_table`. Constructed
                with `DeltaSharingDataStore()` when school pins must be loaded
                and this is omitted.

        Returns:
            A copy of the telemetry frame with canonical identifiers, optional
            Wi-Fi columns under their canonical names, `govt_latitude` and
            `govt_longitude` when a schools row matches, and local-time
            columns `tz_name`, `local_created_timestamp`, `local_date`,
            `local_hour`, `local_day_of_week`, `is_weekday`, and
            `is_operational_hours`.

        Raises:
            ValueError: If the source count is not exactly one, the file
                suffix is unsupported, school pins cannot be resolved, or
                required columns are missing.
            ConnectionError: If `db.test_connection()` returns false.
        """
        frame = self._read_source(
            telemetry_df=telemetry_df,
            file_path=file_path,
            query_name=query_name,
            query_params=query_params,
            db=db,
        )
        frame = canonicalize_telemetry_columns(frame)
        if "govt_latitude" not in frame.columns:
            frame = self._merge_school_pins(
                frame,
                schools_df=schools_df,
                country_iso3=_resolve_country_iso3(country_iso3, query_params),
                delta_store=delta_store,
            )
        if not set(_LOCAL_TIME_SKIP_COLUMNS).issubset(frame.columns):
            frame = enrich_telemetry_with_local_time(
                frame, timestamp_col=timestamp_col
            )
        _require_columns(frame, REQUIRED_TELEMETRY_COLUMNS + LOCAL_TIME_COLUMNS)
        return frame

    def _read_source(
        self,
        *,
        telemetry_df: Optional[pd.DataFrame],
        file_path: Optional[Union[str, Path]],
        query_name: Optional[str],
        query_params: Optional[Mapping[str, Any]],
        db: Any,
    ) -> pd.DataFrame:
        """Read exactly one of a DataFrame, a local file, or a SQL template."""
        selected = sum(
            source is not None
            for source in (telemetry_df, file_path, query_name)
        )
        if selected != 1:
            raise ValueError(
                "Provide exactly one of telemetry_df, file_path, or query_name."
            )
        if telemetry_df is not None:
            return telemetry_df.copy()
        if file_path is not None:
            return self._read_file(Path(file_path))
        return self._read_query(str(query_name), query_params, db)

    def _read_file(self, path: Path) -> pd.DataFrame:
        """Read a CSV or Parquet ledger."""
        suffix = path.suffix.lower()
        if suffix == ".csv":
            return pd.read_csv(path)
        if suffix == ".parquet":
            return pd.read_parquet(path)
        raise ValueError(
            f"Unsupported telemetry file '{path.name}'. Use a .csv or .parquet file."
        )

    def _read_query(
        self,
        query_name: str,
        query_params: Optional[Mapping[str, Any]],
        db: Any,
    ) -> pd.DataFrame:
        """Format a SQL template and read it after a successful connection test."""
        connection = _checked_db_connection(db)
        template_path = self.sql_dir / f"{query_name}.sql"
        raw_sql = template_path.read_text()
        try:
            sql = raw_sql.format(**dict(query_params or {}))
        except KeyError as exc:
            raise ValueError(
                f"SQL template '{query_name}' is missing parameter: {exc.args[0]}"
            ) from exc
        return connection.read_sql_to_dataframe(sql)

    def _merge_school_pins(
        self,
        telemetry_df: pd.DataFrame,
        *,
        schools_df: Optional[pd.DataFrame],
        country_iso3: Optional[str],
        delta_store: Any,
    ) -> pd.DataFrame:
        """Left-join official coordinates onto telemetry by `school_id_giga`."""
        if "school_id_giga" not in telemetry_df.columns:
            raise ValueError(
                "Telemetry frame is missing required columns: school_id_giga"
            )
        if schools_df is None:
            if not country_iso3:
                raise ValueError(
                    "country_iso3 is required to load school coordinates from "
                    "Delta Sharing when govt_latitude is absent and schools_df "
                    "is not provided."
                )
            store = _delta_store_or_default(delta_store)
            schools_df = store.load_table(country_iso3)

        pins = prepare_schools_frame(schools_df)
        return telemetry_df.merge(pins, on="school_id_giga", how="left")
