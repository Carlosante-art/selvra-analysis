-- Oura: one row per day. Scores are Oura's own 0-100 composites; durations, HRV and
-- lowest heart rate come from the night's main sleep period (see ingest_oura.parse);
-- steps are the calendar day's total (daily_activity).

select
    reading_date,
    sleep_score,
    readiness_score,
    total_sleep_seconds,
    deep_sleep_seconds,
    rem_sleep_seconds,
    sleep_efficiency_pct,
    hrv_avg_ms,
    hr_lowest_bpm,
    steps
from {{ source('raw', 'oura_sleep') }}
where reading_date is not null
