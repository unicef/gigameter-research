# Data Loading

Every analysis class loads telemetry through `TelemetryLoader`, so all of them see the same columns. The loader:

1. reads one source: a DataFrame, a `.csv` or `.parquet` file, or a SQL template;
2. renames known synonyms to the canonical names, for example `giga_id_school` to `school_id_giga`;
3. merges official pins as `govt_latitude` and `govt_longitude` when the telemetry does not already have them;
4. converts UTC timestamps to local time at the facility and adds the operational-hours flags.

It never fills `detected_latitude` or `detected_longitude` from IP coordinates in `client_info`. Rows without a Wi-Fi location keep null coordinates and are dropped later by the spatial classes.

## Column Contract

Required after canonicalisation:

| Column | Meaning |
| --- | --- |
| `school_id_giga` | Facility identifier (`giga_id_school` is accepted) |
| `device_id` | Device identifier; may be null for older app versions |
| `detected_latitude`, `detected_longitude` | Google Wi-Fi geolocation result, or null |
| `created_timestamp` | UTC time of the measurement |

Added by the loader:

| Column | Meaning |
| --- | --- |
| `govt_latitude`, `govt_longitude` | Official pin, when one is found |
| `tz_name` | IANA time zone of the facility |
| `local_created_timestamp`, `local_date`, `local_hour`, `local_day_of_week` | Local time fields |
| `is_weekday` | Monday to Friday |
| `is_operational_hours` | 08:00:00 to 19:59:59 local time |

Optional Wi-Fi columns are renamed when present: `detected_bssid` to `detected_wifi_bssid`, `detected_ssid` to `detected_wifi_ssid`, and `detected_wifi_signal` to `wifi_signal_dbm`.

## TelemetryLoader

::: src.utils.data_loader.TelemetryLoader

## Helper Functions

::: src.utils.data_loader.canonicalize_telemetry_columns

::: src.utils.data_loader.prepare_schools_frame

::: src.utils.timezone_enricher.enrich_telemetry_with_local_time

::: src.utils.timezone_enricher.build_school_timezone_map
