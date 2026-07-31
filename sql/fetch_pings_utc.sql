-- ==============================================================================
-- Script Name:     fetch_pings_utc.sql
-- Purpose:         Extracts pure, unaggregated raw ping telemetry in UTC for 
--                  Python 4-state modeling and timezone enrichment.
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
    cpc.id AS connectivity_id,
    cpc.giga_id_school AS school_id_giga,
    s.school_id_govt,
    s.school_name,
    s.country,
    s.iso3_code,
    
    -- Raw UTC Timestamps
    cpc.timestamp AS created_timestamp,
    CAST(DATE_TRUNC('day', cpc.timestamp) AS DATE) AS date,
    cpc.created_at AS record_created_at,

    -- Raw Ping Payload & Telemetry Indicators
    cpc.is_connected,
    cpc.latency AS latency_ms,
    cpc.error_message,

    -- Client & Session Identifiers (Used for session reset & slot deduplication)
    cpc.app_local_uuid,
    cpc.browser_id AS device_id

FROM gigameter_production_db.public.connectivity_ping_checks cpc
INNER JOIN school_lookup s
    ON cpc.giga_id_school = s.school_id_giga
WHERE cpc.timestamp >= CAST('{start_date}' AS TIMESTAMP)
  AND cpc.timestamp <  CAST('{end_date}' AS TIMESTAMP)
ORDER BY cpc.timestamp ASC