-- ==============================================================================
-- Script Name:     fetch_ping_hourly.sql
-- Purpose:         Extracts aggregated hourly time-series ping metrics for 
--                  Section 2 / Pillar 4 Outage & Connectivity Modeling.
-- Dialect:         Trino / Presto
-- Parameters:      {country_iso3}, {lookback_days}
-- ==============================================================================

WITH school_lookup AS (
    SELECT
        school.giga_id_school AS school_id_giga,
        school.external_id AS school_id_govt,
        school.name AS school_name,
        country.name AS country,
        UPPER(TRIM(country.iso3_format)) AS iso3_code,
        COALESCE(tz.timezone, tz_name.timezone, 'UTC') AS timezone,
        school.admin_1_name AS admin_1,
        school.admin_2_name AS admin_2
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

ping_base AS (
    SELECT 
        cpc.id AS connectivity_id,
        cpc.timestamp,
        cpc.is_connected,
        cpc.giga_id_school AS school_id_giga,
        cpc.browser_id AS device_id,
        cpc.latency
    FROM gigameter_production_db.public.connectivity_ping_checks cpc
    WHERE cpc.timestamp >= NOW() - INTERVAL '{lookback_days}' DAY
),

ping_enriched AS (
    SELECT 
        CAST(AT_TIMEZONE(pb.timestamp, sl.timezone) AS TIMESTAMP) AS local_ts,
        pb.is_connected,
        pb.latency,
        pb.device_id,
        sl.*
    FROM ping_base pb 
    INNER JOIN school_lookup sl 
        ON pb.school_id_giga = sl.school_id_giga
),

ping_aggr AS (
    SELECT
        CAST(local_ts AS DATE) AS local_created_date,
        CAST(DATE_TRUNC('hour', local_ts) AS TIMESTAMP) AS local_date_hour,
        EXTRACT(HOUR FROM local_ts) AS local_hour,
        country,
        iso3_code,
        school_id_giga,
        school_id_govt,
        school_name,
        admin_1,
        admin_2,
        device_id,

        COUNT(*) AS total_ping_records,
        4 - COALESCE(COUNT(*), 0) AS missing_pings,
        
        -- Section 2.2: 4-State Classification Aggregations
        SUM(CASE WHEN is_connected = TRUE AND latency IS NOT NULL THEN 1 ELSE 0 END) AS state_a_uptime_count,
        SUM(CASE WHEN is_connected = FALSE THEN 1 ELSE 0 END) AS state_b_downtime_count,
        SUM(CASE WHEN is_connected = TRUE AND latency IS NULL THEN 1 ELSE 0 END) AS state_d_degraded_count,

        AVG(latency) AS avg_latency_ms
    FROM ping_enriched
    GROUP BY
        CAST(local_ts AS DATE),
        CAST(DATE_TRUNC('hour', local_ts) AS TIMESTAMP),
        EXTRACT(HOUR FROM local_ts),
        country,
        iso3_code,
        school_id_giga,
        school_id_govt,
        school_name,
        admin_1,
        admin_2,
        device_id
)

SELECT
    p.local_created_date,
    p.local_date_hour,
    p.local_hour,
    p.device_id,
    p.school_id_giga,
    p.school_id_govt,
    p.school_name,
    p.country,
    p.admin_1,
    p.admin_2,

    -- Operational Window Rule (Strictly 08:00 - 19:59)
    (p.local_hour BETWEEN 8 AND 19) AS is_operational_hours,

    p.total_ping_records,
    p.missing_pings,
    p.state_a_uptime_count,
    p.state_b_downtime_count,
    p.state_d_degraded_count,
    p.avg_latency_ms,

    -- Section 2.3 Formula: Strict Formal Uptime % = State A / (State A + State B) * 100
    CASE 
        WHEN (p.state_a_uptime_count + p.state_b_downtime_count) > 0 
        THEN ROUND(CAST(p.state_a_uptime_count AS DECIMAL(10,2)) / (p.state_a_uptime_count + p.state_b_downtime_count) * 100.0, 2)
        ELSE NULL 
    END AS formal_uptime_pct,

    -- Availability Metric (% of expected 4 pings captured)
    ROUND((1.0 - (p.missing_pings / 4.0)) * 100.0, 2) AS ping_availability_pct

FROM ping_aggr p;