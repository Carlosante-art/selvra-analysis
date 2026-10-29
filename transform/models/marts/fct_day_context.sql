-- One row per day with glucose data: what the event log says about that day,
-- and whether the sensor data suggests a sensor change. Comparing the two shows
-- how complete the log is.
--
-- An evening event (alcohol at 21:00) is attributed to its own date here.
-- Whether it should count for the next day is an analysis decision, made in the pre-registration.

-- The day spine is every day with any data: CGM or wearable. A person without a
-- CGM (wearable-only mode) still gets a full context row per day; the glucose
-- columns in the mart are simply null for days the CGM did not cover.
with aktiviteter as (

    select
        reading_date,
        round(sum(duration_s) / 60.0, 1) as garmin_traningsminuter
    from {{ ref('stg_garmin_activities') }}
    group by reading_date

),

days as (

    select reading_date from {{ ref('fct_glucose_daily') }}
    union
    select reading_date from {{ ref('int_wearable_daily') }}

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

    select * from {{ ref('int_wearable_daily') }}

),

-- Insulin and carbs per day from Nightscout treatments (empty without a
-- configured instance). Bolus units only: temp basals carry rates, not doses.
dosing as (

    select
        treatment_date as reading_date,
        sum(insulin_units)  as insulin_bolus_units,
        sum(carbs_g)        as carbs_logged_g,
        count(*) filter (where insulin_units is not null) as n_boluses
    from {{ ref('stg_nightscout_treatments') }}
    group by treatment_date

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
    bool_or(e.event_type = 'arbete')           is true as is_workday,
    count(e.event_id)                                  as n_events,
    string_agg(e.note, '; ')                           as notes,
    -- Wearable (Oura/Garmin; null om ingen data för dagen)
    sl.sleep_score,
    sl.readiness_score,
    sl.hrv_avg_ms,
    sl.stress_avg,
    sl.stress_max,
    akt.garmin_traningsminuter,
    case
        when akt.garmin_traningsminuter is not null then true
        when sl.wearable_source is not null then false
    end as had_garmin_activity,
    sl.hr_lowest_bpm,
    sl.total_sleep_seconds,
    sl.deep_sleep_seconds,
    sl.rem_sleep_seconds,
    sl.sleep_efficiency_pct,
    sl.steps,
    sl.wearable_source,
    -- Dosering (null utan Nightscout)
    dsg.insulin_bolus_units,
    dsg.carbs_logged_g,
    dsg.n_boluses,
    -- Exposure derived from steps: true/false only when wearable data exists for the day,
    -- null otherwise, so days without data fall out of both study groups.
    case
        when sl.steps is not null
            then sl.steps >= {{ var('high_steps_threshold', 10000) }}
    end as high_steps
from days as d
left join aktiviteter as akt
    on d.reading_date = akt.reading_date
left join events as e
    on d.reading_date between e.start_date and e.end_date
left join inferred_sensor_starts as s
    on d.reading_date = s.reading_date
left join sleep as sl
    on d.reading_date = sl.reading_date
left join dosing as dsg
    on d.reading_date = dsg.reading_date
group by d.reading_date, s.reading_date, sl.sleep_score, sl.readiness_score,
         sl.hrv_avg_ms, sl.stress_avg, sl.stress_max, akt.garmin_traningsminuter,
         sl.wearable_source, sl.hr_lowest_bpm, sl.total_sleep_seconds,
         sl.deep_sleep_seconds, sl.rem_sleep_seconds, sl.sleep_efficiency_pct,
         sl.steps, sl.wearable_source, dsg.insulin_bolus_units, dsg.carbs_logged_g,
         dsg.n_boluses
