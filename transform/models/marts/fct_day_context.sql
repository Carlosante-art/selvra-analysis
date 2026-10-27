-- One row per day with glucose data: what the event log says about that day,
-- and whether the sensor data suggests a sensor change. Comparing the two shows
-- how complete the log is.
--
-- An evening event (alcohol at 21:00) is attributed to its own date here.
-- Whether it should count for the next day is an analysis decision, made in the pre-registration.

with days as (

    select reading_date from {{ ref('fct_glucose_daily') }}

),

events as (

    select * from {{ ref('stg_personal_events') }}

),

sensor_sessions as (

    select arg_min(reading_date, reading_at) as start_date
    from {{ ref('int_cgm_flagged') }}
    where sensor_session_id > 1
    group by sensor_session_id

),

-- Two inferred sessions can start on the same day; one row per day.
inferred_sensor_starts as (

    select distinct start_date as reading_date
    from sensor_sessions

),

sleep as (

    select * from {{ ref('stg_oura_sleep') }}

)

select
    d.reading_date,
    bool_or(e.event_type = 'sjukdom')          is true as is_ill,
    bool_or(e.event_type = 'sensorbyte')       is true as sensor_change_logged,
    s.reading_date is not null                         as sensor_change_inferred,
    bool_or(e.event_type = 'alkohol')          is true as had_alcohol,
    bool_or(e.event_type = 'traning')          is true as had_training,
    bool_or(e.event_type = 'resa')             is true as is_travelling,
    bool_or(e.event_type = 'stress')           is true as had_stress,
    bool_or(e.event_type = 'menstruation')     is true as is_menstruating,
    bool_or(e.event_type = 'medicinandring')   is true as had_medication_change,
    bool_or(e.event_type = 'annat')            is true as had_other_event,
    count(e.event_id)                                  as n_events,
    string_agg(e.note, '; ')                           as notes,
    -- Oura sleep (null om OURA_TOKEN saknas eller saknad dag)
    sl.sleep_score,
    sl.readiness_score,
    sl.hrv_avg,
    sl.hr_lowest_bpm,
    sl.total_sleep_seconds,
    sl.deep_sleep_seconds,
    sl.rem_sleep_seconds,
    sl.sleep_efficiency_pct
from days as d
left join events as e
    on d.reading_date between e.start_date and e.end_date
left join inferred_sensor_starts as s
    on d.reading_date = s.reading_date
left join sleep as sl
    on d.reading_date = sl.reading_date
group by d.reading_date, s.reading_date, sl.sleep_score, sl.readiness_score,
         sl.hrv_avg, sl.hr_lowest_bpm, sl.total_sleep_seconds,
         sl.deep_sleep_seconds, sl.rem_sleep_seconds, sl.sleep_efficiency_pct
