-- ==============================================================================
-- Script Name:     fetch_spatial_telemetry_coverage.sql
-- Purpose:         Aggregates country-level school coverage metrics for active
--                  Wi-Fi SSID submissions and Google API resolved spatial 
--                  coordinates (strict no-IP policy).
-- Dialect:         Trino / Presto
-- Parameters:      {min_app_version}
-- ==============================================================================

WITH school_lookup AS (
    SELECT
        school.giga_id_school AS school_id_giga,
        school.name AS school_name,
        country.name AS country,
        UPPER(TRIM(country.iso3_format)) AS iso3_code
    FROM gigameter_production_db.public.school
    LEFT JOIN gigameter_production_db.public.country
        ON country.id = school.country_id
    WHERE school.deleted IS NULL
      AND country.iso3_format IS NOT NULL
),

school_telemetry_summary AS (
    SELECT 
        s.iso3_code,
        s.country,
        m.giga_id_school AS school_id_giga,
        
        -- Evaluates if the school has transmitted at least one valid Wi-Fi SSID
        BOOL_OR(
            JSON_EXTRACT_SCALAR(CAST(m.wifi_connections AS JSON), '$[0].ssid') IS NOT NULL
            AND JSON_EXTRACT_SCALAR(CAST(m.wifi_connections AS JSON), '$[0].ssid') <> ''
        ) AS has_sent_ssid,

        -- Evaluates if the school has resolved valid Wi-Fi coordinates (strict no-IP fallback)
        BOOL_OR(
            m.detected_latitude IS NOT NULL 
            AND m.detected_longitude IS NOT NULL
        ) AS has_detected_coords

    FROM gigameter_production_db.public.measurements m
    INNER JOIN school_lookup s 
        ON m.giga_id_school = s.school_id_giga
    WHERE m.source = 'DailyCheckApp'
      AND TRY(TRANSFORM(SPLIT(REGEXP_EXTRACT(m.app_version, '^[0-9]+(\.[0-9]+)*'), '.'), x -> CAST(x AS INTEGER)))
          >= TRANSFORM(SPLIT('{min_app_version}', '.'), x -> CAST(x AS INTEGER))
    GROUP BY 
        s.iso3_code,
        s.country,
        m.giga_id_school
)

SELECT 
    iso3_code,
    country,
    COUNT(*) AS total_schools,
    
    -- Absolute school counts per capability
    COUNT(*) FILTER (WHERE has_sent_ssid = TRUE) AS schools_with_ssid,
    COUNT(*) FILTER (WHERE has_detected_coords = TRUE) AS schools_with_detected_coords,
    
    -- Dual coverage percentages
    ROUND(
        COUNT(*) FILTER (WHERE has_sent_ssid = TRUE) * 100.0 / COUNT(*), 
        2
    ) AS ssid_coverage_percentage,
    
    ROUND(
        COUNT(*) FILTER (WHERE has_detected_coords = TRUE) * 100.0 / COUNT(*), 
        2
    ) AS coords_coverage_percentage

FROM school_telemetry_summary
GROUP BY 
    iso3_code,
    country
ORDER BY 
    total_schools DESC, 
    iso3_code ASC