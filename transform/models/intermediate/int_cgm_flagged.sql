-- One row per reading with artefact flags. Nothing is removed: every downstream metric
-- can be computed with and without flagged readings, and the difference is itself a finding.
--
-- Flag epistemics:
--   flag_censored            observed  (the export says Low/High)
--   flag_early_sensor        derived   (first 24 h of an inferred sensor session)
--   flag_implausible_jump    derived   (rate between consecutive readings above a physiological limit)
--   flag_compression_low     interpreted (heuristic: a fast night-time drop below range that recovers fast)

with segments as (

    select * from {{ ref('int_cgm_segments') }}

),

low_marked as (

    select
        *,
        glucose_mmol < {{ var('range_low_mmol') }} as is_low,
        lag(glucose_mmol < {{ var('range_low_mmol') }})
            over (order by reading_at, reading_id) as prev_is_low
    from segments

),

low_runs_numbered as (

    select
        *,
        sum(case when is_low and (prev_is_low is null or not prev_is_low or starts_segment) then 1 else 0 end)
            over (order by reading_at, reading_id rows unbounded preceding) as low_run_id
    from low_marked

),

low_runs as (

    select
        low_run_id,
        min(reading_at)   as run_start_at,
        max(reading_at)   as run_end_at,
        min(glucose_mmol) as nadir_mmol
    from low_runs_numbered
    where is_low
    group by low_run_id

),

-- Value about 20 minutes before the run started (latest reading at or before that time)
low_runs_with_pre as (

    select
        r.*,
        s.glucose_mmol as pre_mmol,
        s.reading_at   as pre_at
    from low_runs as r
    asof left join segments as s
        on s.reading_at <= r.run_start_at - interval 20 minute

),

-- Highest value within 45 minutes after the run ended
low_runs_with_post as (

    select
        r.*,
        max(s.glucose_mmol) as post_max_mmol
    from low_runs_with_pre as r
    left join segments as s
        on s.reading_at > r.run_end_at
       and s.reading_at <= r.run_end_at + interval 45 minute
    group by all

),

compression_runs as (

    select low_run_id
    from low_runs_with_post
    where extract(hour from run_start_at) between 0 and 5
      and date_diff('minute', run_start_at, run_end_at) <= 45
      and date_diff('minute', pre_at, run_start_at) <= 30
      and pre_mmol - nadir_mmol >= 2.0
      and post_max_mmol >= pre_mmol - 1.0

)

select
    l.reading_id,
    l.reading_at,
    l.reading_date,
    l.glucose_mmol,
    l.censored,
    l.transmitter_id,
    l.segment_id,
    l.sensor_session_id,
    l.gap_minutes,
    l.hours_since_sensor_start,
    l.censored is not null                                         as flag_censored,
    l.hours_since_sensor_start < {{ var('early_sensor_hours') }}   as flag_early_sensor,
    coalesce(
        not l.starts_segment
        and l.gap_minutes > 0
        and abs(l.glucose_mmol - l.prev_glucose_mmol) / l.gap_minutes
            > {{ var('implausible_rate_mmol_per_min') }},
        false)                                                     as flag_implausible_jump,
    coalesce(l.is_low and c.low_run_id is not null, false)         as flag_compression_low
from low_runs_numbered as l
left join compression_runs as c
    on l.low_run_id = c.low_run_id and l.is_low
