-- One wearable row per day, whichever source has data. If both a ring and a watch
-- loaded the same day, Garmin wins the tie (alphabetical order below decides).
-- wearable_source states where each row came from, so the marts stay honest about
-- which device produced a value.

with unioned as (

    select
        reading_date,
        sleep_score,
        readiness_score,
        total_sleep_seconds,
        deep_sleep_seconds,
        rem_sleep_seconds,
        sleep_efficiency_pct,
        hrv_avg_ms,
        stress_avg,
        stress_max,
        hr_lowest_bpm,
        steps,
        'garmin' as wearable_source
    from {{ ref('stg_garmin_daily') }}

    union all

    select
        reading_date,
        sleep_score,
        readiness_score,
        total_sleep_seconds,
        deep_sleep_seconds,
        rem_sleep_seconds,
        sleep_efficiency_pct,
        hrv_avg_ms,
        stress_avg,
        stress_max,
        hr_lowest_bpm,
        steps,
        'oura' as wearable_source
    from {{ ref('stg_oura_sleep') }}

)

select
    reading_date,
    sleep_score,
    readiness_score,
    total_sleep_seconds,
    deep_sleep_seconds,
    rem_sleep_seconds,
    sleep_efficiency_pct,
    hrv_avg_ms,
    stress_avg,
    stress_max,
    hr_lowest_bpm,
    steps,
    wearable_source
from unioned
qualify row_number() over (partition by reading_date order by wearable_source) = 1
