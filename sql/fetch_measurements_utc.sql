-- ==============================================================================
-- Script Name:     fetch_measurements_utc.sql
-- Purpose:         Pure UTC baseline extract for Python post-processing
-- Dialect:         Trino / Presto
-- Parameters:      {country_iso3}, {start_date}, {end_date}
-- ==============================================================================

WITH school_lookup AS (
    SELECT
        school.giga_id_school AS school_id_giga,
        school.external_id AS school_id_govt,
        school.name AS school_name,
        country.name AS country,
        UPPER(TRIM(country.iso3_format)) AS iso3_code
    FROM gigameter_production_db.public.school
    LEFT JOIN gigameter_production_db.public.country
        ON country.id = school.country_id
    WHERE school.deleted IS NULL
        AND UPPER(TRIM(country.iso3_format)) = '{country_iso3}'
)

SELECT
    m.id AS measurement_id,
    m.giga_id_school AS school_id_giga,
    s.school_name,
    s.school_id_govt,
    s.country,
    s.iso3_code,
    
    -- Raw UTC Timestamp
    m.created_at AS created_timestamp,
    CAST(DATE_TRUNC('day', m.created_at) AS DATE) AS date,

    -- Throughput Unit Conversions (kbps -> Mbps)
    ROUND(CAST(m.download AS DOUBLE) / 1000.0, 2) AS download_speed_mbps,
    ROUND(CAST(m.upload AS DOUBLE) / 1000.0, 2) AS upload_speed_mbps,
    m.latency AS latency_ms,

    -- Data Volume Conversions (Bytes -> GB)
    ROUND((CAST(m.data_downloaded AS DOUBLE) / 1000.0) / 1048576.0, 4) AS data_downloaded_gb,
    ROUND((CAST(m.data_uploaded AS DOUBLE) / 1000.0) / 1048576.0, 4) AS data_uploaded_gb,

    -- Spatial Geolocation Fields
    m.detected_latitude,
    m.detected_longitude,
    m.detected_location_accuracy,

    -- Wi-Fi Active Association
    JSON_EXTRACT_SCALAR(CAST(m.wifi_connections AS JSON), '$[0].ssid') AS detected_wifi_ssid,
    JSON_EXTRACT_SCALAR(CAST(m.wifi_connections AS JSON), '$[0].bssid') AS detected_wifi_bssid,
    CAST(JSON_EXTRACT_SCALAR(CAST(m.wifi_connections AS JSON), '$[0].signalLevel') AS DECIMAL(10,2)) AS wifi_signal_dbm,

        -- Client & Server Routing Details
    JSON_EXTRACT_SCALAR(CAST(m.server_info AS JSON), '$.City') AS server_location,
    JSON_EXTRACT_SCALAR(CAST(m.client_info AS JSON), '$.ISP') AS detected_isp_raw,
    JSON_EXTRACT_SCALAR(CAST(m.client_info AS JSON), '$.ASN') AS detected_isp_asn,

        -- =========================================================================
    -- Section 3: NDT7 Diagnostic Payload Parsing
    -- =========================================================================

    -- Throughput Metrics (Mbps)
    CAST(JSON_EXTRACT_SCALAR(CAST(m.results AS JSON), '$["NDTResult.S2C"].LastClientMeasurement.MeanClientMbps') AS DOUBLE) AS ndt7_download_mbps,
    CAST(JSON_EXTRACT_SCALAR(CAST(m.results AS JSON), '$["NDTResult.C2S"].LastClientMeasurement.MeanClientMbps') AS DOUBLE) AS ndt7_upload_mbps,

        -- Test Duration & Transferred Bytes (Client Measurement)
    CAST(JSON_EXTRACT_SCALAR(CAST(m.results AS JSON), '$["NDTResult.S2C"].LastClientMeasurement.ElapsedTime') AS DOUBLE) AS s2c_client_elapsed_time_sec,
    CAST(JSON_EXTRACT_SCALAR(CAST(m.results AS JSON), '$["NDTResult.C2S"].LastClientMeasurement.ElapsedTime') AS DOUBLE) AS c2s_client_elapsed_time_sec,
    CAST(JSON_EXTRACT_SCALAR(CAST(m.results AS JSON), '$["NDTResult.S2C"].LastClientMeasurement.NumBytes') AS BIGINT) AS s2c_client_num_bytes,
    CAST(JSON_EXTRACT_SCALAR(CAST(m.results AS JSON), '$["NDTResult.C2S"].LastClientMeasurement.NumBytes') AS BIGINT) AS c2s_client_num_bytes,
    ROUND(CAST(JSON_EXTRACT_SCALAR(CAST(m.results AS JSON), '$["NDTResult.S2C"].LastClientMeasurement.NumBytes') AS DOUBLE) / 1048576.0, 3) AS s2c_client_transferred_mb,
    ROUND(CAST(JSON_EXTRACT_SCALAR(CAST(m.results AS JSON), '$["NDTResult.C2S"].LastClientMeasurement.NumBytes') AS DOUBLE) / 1048576.0, 3) AS c2s_client_transferred_mb,

    -- Bufferbloat Metrics (Microseconds -> Milliseconds)
    CAST(JSON_EXTRACT_SCALAR(CAST(m.results AS JSON), '$["NDTResult.S2C"].LastServerMeasurement.TCPInfo.RTT') AS DOUBLE) / 1000.0 AS working_latency_ms,
    CAST(JSON_EXTRACT_SCALAR(CAST(m.results AS JSON), '$["NDTResult.S2C"].LastServerMeasurement.BBRInfo.MinRTT') AS DOUBLE) / 1000.0 AS baseline_latency_ms,
    (CAST(JSON_EXTRACT_SCALAR(CAST(m.results AS JSON), '$["NDTResult.S2C"].LastServerMeasurement.TCPInfo.RTT') AS DOUBLE) - 
     CAST(JSON_EXTRACT_SCALAR(CAST(m.results AS JSON), '$["NDTResult.S2C"].LastServerMeasurement.BBRInfo.MinRTT') AS DOUBLE)) / 1000.0 AS bufferbloat_delta_ms,

    -- TCP Packet Retransmissions & BBR Capacity
    CAST(JSON_EXTRACT_SCALAR(CAST(m.results AS JSON), '$["NDTResult.S2C"].LastServerMeasurement.TCPInfo.TotalRetrans') AS BIGINT) AS tcp_total_retrans,
    CAST(JSON_EXTRACT_SCALAR(CAST(m.results AS JSON), '$["NDTResult.S2C"].LastServerMeasurement.BBRInfo.BW') AS DOUBLE) AS bbr_bottleneck_bw,

    m.app_version,
    m.browser_id,
    m.device_hardware_id AS device_id

FROM gigameter_production_db.public.measurements m
INNER JOIN school_lookup s
    ON m.giga_id_school = s.school_id_giga
WHERE m.source = 'DailyCheckApp'
  AND m.created_at >= CAST('{start_date}' AS TIMESTAMP)
  AND m.created_at <  CAST('{end_date}' AS TIMESTAMP)