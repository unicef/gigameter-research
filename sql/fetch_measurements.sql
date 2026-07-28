-- ==============================================================================
-- Script Name:     fetch_measurements.sql
-- Purpose:         General extraction of raw GigaMeter mobile app measurements 
--                  and NDT7 diagnostic payloads (preserves all records).
-- Dialect:         Trino / Presto (Python Driver / Notebook Ready)
-- Parameters:      {country_iso3}, {start_date}, {end_date}
-- Rules:           GigaMeter v2.2 - Section 2 Operational Window & NDT7 Schema
-- ==============================================================================

WITH school_lookup AS (
    SELECT
        school.giga_id_school AS school_id_giga,
        school.external_id AS school_id_govt,
        school.name AS school_name,
        country.name AS country,
        country.code AS iso2_code,
        UPPER(TRIM(country.iso3_format)) AS iso3_code,
        COALESCE(tz.timezone, tz_name.timezone, 'UTC') AS timezone
    FROM gigameter_production_db.public.school
    LEFT JOIN gigameter_production_db.public.country
        ON country.id = school.country_id
    LEFT JOIN default.country_timezones tz
        ON country.iso3_format = tz.iso3
    LEFT JOIN default.country_timezones tz_name
        ON LOWER(country.name) = LOWER(tz_name.country)
    WHERE school.deleted IS NULL
        AND UPPER(TRIM(country.iso3_format)) = '{country_iso3}'
),

measurements_base AS (
    SELECT
        id AS measurement_id,
        giga_id_school AS school_id_giga,
        created_at AS created_timestamp,
        CAST(DATE_TRUNC('day', created_at) AS DATE) AS date,
        download,
        upload,
        latency,
        data_downloaded,
        data_uploaded,
        data_usage,
        results,
        client_info,
        server_info,
        wifi_connections,
        detected_latitude,
        detected_longitude,
        detected_location_accuracy,
        app_version,
        notes,
        browser_id,
        device_hardware_id AS device_id, 
        installed_path,
        windows_username
    FROM gigameter_production_db.public.measurements
    WHERE source = 'DailyCheckApp'
      AND created_at >= CAST('{start_date}' AS TIMESTAMP)
      AND created_at <  CAST('{end_date}' AS TIMESTAMP)
    -- Note: Coordinates are NOT filtered here to preserve all speed tests.
),

measurements_enriched AS (
    SELECT
        m.*,
        s.school_name,
        s.school_id_govt,
        s.country,
        s.iso3_code,
        s.timezone,
        AT_TIMEZONE(CAST(m.created_timestamp AS TIMESTAMP WITH TIME ZONE), s.timezone) AS local_created_timestamp
    FROM measurements_base m
    INNER JOIN school_lookup s
        ON m.school_id_giga = s.school_id_giga
)

SELECT
    measurement_id,
    school_id_giga,
    school_name,
    school_id_govt,
    country,
    iso3_code,
    created_timestamp,
    date,
    CAST(local_created_timestamp AS TIMESTAMP) AS local_created_timestamp,
    EXTRACT(HOUR FROM local_created_timestamp) AS local_hour_of_measurement,
    FORMAT_DATETIME(local_created_timestamp, 'EEEE') AS local_day_of_week,

    -- Section 2: Active Operational Hours Window (08:00 - 19:59 local device time)
    CASE 
        WHEN EXTRACT(HOUR FROM local_created_timestamp) BETWEEN 8 AND 19 THEN TRUE 
        ELSE FALSE 
    END AS is_operational_hours,

    -- Throughput Unit Conversions (kbps -> Mbps)
    ROUND(CAST(download AS DOUBLE) / 1000.0, 2) AS download_speed_mbps,
    ROUND(CAST(upload AS DOUBLE) / 1000.0, 2) AS upload_speed_mbps,
    latency AS latency_ms,

    -- Data Volume Conversions (Bytes -> GB)
    ROUND((CAST(data_downloaded AS DOUBLE) / 1000.0) / 1048576.0, 4) AS data_downloaded_gb,
    ROUND((CAST(data_uploaded AS DOUBLE) / 1000.0) / 1048576.0, 4) AS data_uploaded_gb,

    -- Spatial Coordinates & Active Wi-Fi Association
    detected_latitude,
    detected_longitude,
    detected_location_accuracy,

    -- Wi-Fi Active Association
    JSON_EXTRACT_SCALAR(CAST(wifi_connections AS JSON), '$[0].ssid') AS detected_wifi_ssid,
    JSON_EXTRACT_SCALAR(CAST(wifi_connections AS JSON), '$[0].bssid') AS detected_wifi_bssid,
    CAST(JSON_EXTRACT_SCALAR(CAST(wifi_connections AS JSON), '$[0].signalLevel') AS DECIMAL(10,2)) AS wifi_signal_dbm,

    -- Client & Server Routing Details
    JSON_EXTRACT_SCALAR(CAST(server_info AS JSON), '$.City') AS server_location,
    JSON_EXTRACT_SCALAR(CAST(client_info AS JSON), '$.ISP') AS detected_isp_raw,
    JSON_EXTRACT_SCALAR(CAST(client_info AS JSON), '$.ASN') AS detected_isp_asn,

    -- =========================================================================
    -- Section 3: NDT7 Diagnostic Payload Parsing
    -- =========================================================================
    
    -- Throughput Metrics (Mbps)
    CAST(JSON_EXTRACT_SCALAR(CAST(results AS JSON), '$["NDTResult.S2C"].LastClientMeasurement.MeanClientMbps') AS DOUBLE) AS ndt7_download_mbps,
    CAST(JSON_EXTRACT_SCALAR(CAST(results AS JSON), '$["NDTResult.C2S"].LastClientMeasurement.MeanClientMbps') AS DOUBLE) AS ndt7_upload_mbps,

    -- Test Duration & Transferred Bytes (Client Measurement)
    CAST(JSON_EXTRACT_SCALAR(CAST(results AS JSON), '$["NDTResult.S2C"].LastClientMeasurement.ElapsedTime') AS DOUBLE) AS s2c_client_elapsed_time_sec,
    CAST(JSON_EXTRACT_SCALAR(CAST(results AS JSON), '$["NDTResult.C2S"].LastClientMeasurement.ElapsedTime') AS DOUBLE) AS c2s_client_elapsed_time_sec,
    CAST(JSON_EXTRACT_SCALAR(CAST(results AS JSON), '$["NDTResult.S2C"].LastClientMeasurement.NumBytes') AS BIGINT) AS s2c_client_num_bytes,
    CAST(JSON_EXTRACT_SCALAR(CAST(results AS JSON), '$["NDTResult.C2S"].LastClientMeasurement.NumBytes') AS BIGINT) AS c2s_client_num_bytes,
    ROUND(CAST(JSON_EXTRACT_SCALAR(CAST(results AS JSON), '$["NDTResult.S2C"].LastClientMeasurement.NumBytes') AS DOUBLE) / 1048576.0, 3) AS s2c_client_transferred_mb,
    ROUND(CAST(JSON_EXTRACT_SCALAR(CAST(results AS JSON), '$["NDTResult.C2S"].LastClientMeasurement.NumBytes') AS DOUBLE) / 1048576.0, 3) AS c2s_client_transferred_mb,

    -- Bufferbloat Metrics (Microseconds -> Milliseconds)
    CAST(JSON_EXTRACT_SCALAR(CAST(results AS JSON), '$["NDTResult.S2C"].LastServerMeasurement.TCPInfo.RTT') AS DOUBLE) / 1000.0 AS working_latency_ms,
    CAST(JSON_EXTRACT_SCALAR(CAST(results AS JSON), '$["NDTResult.S2C"].LastServerMeasurement.BBRInfo.MinRTT') AS DOUBLE) / 1000.0 AS baseline_latency_ms,
    (CAST(JSON_EXTRACT_SCALAR(CAST(results AS JSON), '$["NDTResult.S2C"].LastServerMeasurement.TCPInfo.RTT') AS DOUBLE) - 
     CAST(JSON_EXTRACT_SCALAR(CAST(results AS JSON), '$["NDTResult.S2C"].LastServerMeasurement.BBRInfo.MinRTT') AS DOUBLE)) / 1000.0 AS bufferbloat_delta_ms,

    -- TCP Packet Retransmissions & BBR Capacity
    CAST(JSON_EXTRACT_SCALAR(CAST(results AS JSON), '$["NDTResult.S2C"].LastServerMeasurement.TCPInfo.TotalRetrans') AS BIGINT) AS tcp_total_retrans,
    CAST(JSON_EXTRACT_SCALAR(CAST(results AS JSON), '$["NDTResult.S2C"].LastServerMeasurement.BBRInfo.BW') AS DOUBLE) AS bbr_bottleneck_bw,

    app_version,
    browser_id,
    device_id
FROM measurements_enriched