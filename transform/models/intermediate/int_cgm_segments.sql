-- Adds recording structure: gaps, contiguous segments and inferred sensor sessions.
-- Sensor changes are INFERRED (transmitter ID change, or a gap long enough for warm-up).
-- Confirm against the personal event log before treating them as observed.

with ordered as (

    select
        *,
        lag(reading_at)     over (order by reading_at, reading_id) as prev_reading_at,
        lag(glucose_mmol)   over (order by reading_at, reading_id) as prev_glucose_mmol,
        lag(transmitter_id) over (order by reading_at, reading_id) as prev_transmitter_id
    from {{ ref('int_cgm_readings') }}

),

with_gaps as (

    select
        *,
        date_diff('second', prev_reading_at, reading_at) / 60.0 as gap_minutes
    from ordered

),

marked as (

    select
        *,
        prev_reading_at is null
            or gap_minutes > {{ var('segment_gap_minutes') }}                as starts_segment,
        prev_reading_at is null
            or transmitter_id is distinct from prev_transmitter_id
            or gap_minutes >= {{ var('sensor_change_gap_minutes') }}         as starts_sensor_session
    from with_gaps

),

numbered as (

    select
        *,
        sum(case when starts_segment then 1 else 0 end)
            over (order by reading_at, reading_id rows unbounded preceding)  as segment_id,
        sum(case when starts_sensor_session then 1 else 0 end)
            over (order by reading_at, reading_id rows unbounded preceding)  as sensor_session_id
    from marked

)

select
    *,
    date_diff('second',
        min(reading_at) over (partition by sensor_session_id),
        reading_at) / 3600.0 as hours_since_sensor_start
from numbered
