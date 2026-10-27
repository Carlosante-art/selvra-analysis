-- Garmin: one row per day. sleep_score is Garmin's own 0-100 composite; durations come
-- from the night's sleep, HRV is the night's average (ms), hr_lowest_bpm is Garmin's
-- daily resting heart rate (lowest 30-minute average of the day, not the night's lowest);
-- steps are the calendar day's total. readiness_score and sleep_efficiency_pct are always
-- null: Garmin has no equivalent of Oura's measures (see ingest_garmin.parse_day).

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
from {{ source('raw', 'garmin_daily') }}
where reading_date is not null
