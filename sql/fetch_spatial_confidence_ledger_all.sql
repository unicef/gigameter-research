-- ==============================================================================
-- Script Name:     fetch_spatial_confidence_ledger.sql
-- Purpose:         Extracts unnested BSSID telemetry, spatial accuracy metrics,
--                  and native BSSID array density for Pillars 1, 2, and 3.
-- Dialect:         Trino / Presto
-- Parameters:      {start_date}, {end_date}, {min_app_version}
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
),

measurements_parsed AS (
    SELECT 
        m.id AS measurement_id,
        m.giga_id_school AS school_id_giga,
        m.device_hardware_id AS device_id,
        m.browser_id,
        m.created_at AS created_timestamp,
        CAST(DATE_TRUNC('day', m.created_at) AS DATE) AS date,
        
        -- Spatial Geolocation Fields
        m.detected_latitude,
        m.detected_longitude,
        m.detected_location_accuracy,
        m.app_version,
        
        -- Cast native JSON once for cardinality evaluation and unnesting
        CAST(m.wifi_connections AS ARRAY(JSON)) AS wifi_array,
        
        -- Compute BSSID Array Density Metric (0 for ambient scans)
        COALESCE(
            TRY(CARDINALITY(CAST(m.wifi_connections AS ARRAY(JSON)))), 
            0
        ) AS bssid_count

    FROM gigameter_production_db.public.measurements m
    WHERE m.source = 'DailyCheckApp' 
      AND TRY(TRANSFORM(SPLIT(REGEXP_EXTRACT(m.app_version, '^[0-9]+(\.[0-9]+)*'), '.'), x -> CAST(x AS INTEGER)))
          >= TRANSFORM(SPLIT('{min_app_version}', '.'), x -> CAST(x AS INTEGER))
      AND m.created_at >= CAST('{start_date}' AS TIMESTAMP)
      AND m.created_at <  CAST('{end_date}' AS TIMESTAMP)
      
      -- Exclude unresolvable Google API requests
      AND m.detected_latitude IS NOT NULL 
      AND m.detected_longitude IS NOT NULL
)

SELECT 
    mp.measurement_id,
    mp.school_id_giga,
    s.school_id_govt,
    s.school_name,
    s.country,
    s.iso3_code,
    mp.device_id,
    mp.browser_id,
    
    -- Raw UTC Timestamp
    mp.created_timestamp,
    mp.date,
    
    -- Spatial Geolocation Fields
    mp.detected_latitude,
    mp.detected_longitude,
    mp.detected_location_accuracy,
    mp.bssid_count,
    mp.app_version,
    
    -- Extract Unnested Wi-Fi Fields (NULL for ambient scans)
    JSON_EXTRACT_SCALAR(wifi_node, '$.ssid') AS detected_wifi_ssid,
    JSON_EXTRACT_SCALAR(wifi_node, '$.bssid') AS detected_wifi_bssid,
    CAST(JSON_EXTRACT_SCALAR(wifi_node, '$.signalLevel') AS DECIMAL(10,2)) AS wifi_signal_dbm

FROM measurements_parsed mp
INNER JOIN school_lookup s
    ON mp.school_id_giga = s.school_id_giga

-- LEFT JOIN UNNEST preserves ambient scans (where wifi_array is empty)
LEFT JOIN UNNEST(mp.wifi_array) AS t(wifi_node) ON TRUE