-- ==============================================================================
-- Script Name:     fetch_countries_with_detected_coords.sql
-- Purpose:         Returns countries with at least 1 school that has valid,
--                  Wi-Fi resolved spatial coordinates (strict No-IP policy).
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

schools_with_coords AS (
    SELECT 
        s.iso3_code,
        s.country,
        m.giga_id_school AS school_id_giga
    FROM gigameter_production_db.public.measurements m
    INNER JOIN school_lookup s 
        ON m.giga_id_school = s.school_id_giga
    WHERE m.source = 'DailyCheckApp'
      AND TRY(TRANSFORM(SPLIT(REGEXP_EXTRACT(m.app_version, '^[0-9]+(\.[0-9]+)*'), '.'), x -> CAST(x AS INTEGER)))
          >= TRANSFORM(SPLIT('{min_app_version}', '.'), x -> CAST(x AS INTEGER))
      -- Filter out unresolvable Google API requests (Strict No-IP Policy)
      AND m.detected_latitude IS NOT NULL 
      AND m.detected_longitude IS NOT NULL
    GROUP BY 
        s.iso3_code,
        s.country,
        m.giga_id_school
)

SELECT 
    iso3_code,
    country,
    COUNT(DISTINCT school_id_giga) AS schools_with_detected_coords
FROM schools_with_coords
GROUP BY 
    iso3_code,
    country
HAVING COUNT(DISTINCT school_id_giga) >= 1
ORDER BY 
    schools_with_detected_coords DESC, 
    country ASC