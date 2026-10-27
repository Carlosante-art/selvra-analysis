-- Clarity exports: one row per glucose reading (EGV), typed, in mmol/L, deduplicated across
-- overlapping exports. int_cgm_readings combines this with Dexcom Share.
-- Low/High are kept as censored values at the sensor limits, never dropped.
--
-- Time: Clarity exports local wall-clock time without a zone. Each reading gets
--   reading_at        the instant, timestamptz (UTC). Use this for ordering, gaps and durations.
--   reading_at_local  wall-clock time in var('local_timezone'). Use this for time-of-day.
--   reading_date      the local calendar date. Use this for "per day".
--
-- Daylight saving time:
--   Autumn: the hour 02:00-02:59 occurs twice. Readings in it are ordered by transmitter time
--     (the sensor's own monotonic clock), falling back to file row order. The first pass through
--     the hour is summer time, everything after the wall clock jumps back is winter time.
--     A reading whose wall time repeats an earlier reading's exactly is also second pass.
--   Spring: 02:00-02:59 does not exist. A receiver should never export it. If one does, it is
--     kept, read at +01:00, and flagged local_time_invalid: its exact instant is unknown.
-- Limitation: the passes are resolved within one export file. If an autumn repeated hour is
-- split across two files, the later file cannot tell. Export whole days to avoid this; the
-- test assert_no_readings_lost fails if readings collapse.

{% set tz = var('local_timezone') %}

with source as (

    select * from {{ source('raw', 'clarity_events') }}
    where event_type = 'EGV' and ts_raw <> ''

),

typed as (

    select
        strptime(ts_raw, '%Y-%m-%dT%H:%M:%S')                    as local_wall,
        glucose_raw,
        case glucose_raw
            when 'Low'  then 'low'  -- English (US export)
            when 'High' then 'high' -- English (US export)
            when 'Lågt' then 'low'  -- Swedish (EU export)
            when 'Högt' then 'high' -- Swedish (EU export)
        end as censored,
        case glucose_unit
            when 'mmol/L' then try_cast(replace(glucose_raw, ',', '.') as double)
            when 'mg/dL'  then try_cast(glucose_raw as double) / 18.016
        end                                                       as glucose_numeric,
        nullif(transmitter_id, '')                                as transmitter_id,
        nullif(source_device_id, '')                              as source_device_id,
        source_file,
        try_cast(source_row as integer)                           as source_row,
        try_cast(transmitter_time_raw as bigint)                  as transmitter_time
    from source

),

zoned as (

    select
        *,
        timezone('{{ tz }}', local_wall)                          as utc_guess
    from typed

),

resolved as (

    select
        *,
        timezone('{{ tz }}', utc_guess - interval 1 hour) = local_wall as earlier_also_matches,
        timezone('{{ tz }}', utc_guess + interval 1 hour) = local_wall as later_also_matches,
        timezone('{{ tz }}', utc_guess) <> local_wall                  as local_time_invalid
    from zoned

),

ambiguous as (

    select
        *,
        earlier_also_matches or later_also_matches as is_ambiguous
    from resolved

),

-- Second pass through the repeated hour: the wall clock has jumped back, or the exact wall
-- time has already been seen. Computed only among ambiguous readings of the same file and sensor.
passes as (

    select
        *,
        local_wall < max(local_wall) over (
            partition by source_file, coalesce(transmitter_id, ''), is_ambiguous, cast(local_wall as date)
            order by transmitter_time nulls last, source_row
            rows between unbounded preceding and 1 preceding) - interval 2 minute
        as wall_jumped_back,
        row_number() over (
            partition by source_file, coalesce(transmitter_id, ''), is_ambiguous, cast(local_wall as date), local_wall
            order by transmitter_time nulls last, source_row) as wall_repeat
    from ambiguous

),

occurrences as (

    select
        *,
        case
            when not is_ambiguous then 1
            when coalesce(bool_or(wall_jumped_back) over (
                    partition by source_file, coalesce(transmitter_id, ''), is_ambiguous, cast(local_wall as date)
                    order by transmitter_time nulls last, source_row
                    rows unbounded preceding), false)
                 or wall_repeat >= 2 then 2
            else 1
        end as wall_occurrence
    from passes

),

instants as (

    select
        *,
        case
            when is_ambiguous and wall_occurrence >= 2
                then case when later_also_matches then utc_guess + interval 1 hour else utc_guess end
            when is_ambiguous
                then case when earlier_also_matches then utc_guess - interval 1 hour else utc_guess end
            else utc_guess
        end as reading_at
    from occurrences

),

valued as (

    select
        *,
        round(case censored
            when 'low'  then {{ var('sensor_low_mmol') }}
            when 'high' then {{ var('sensor_high_mmol') }}
            else glucose_numeric
        end, 1) as glucose_mmol
    from instants

),

deduplicated as (

    select *
    from valued
    qualify row_number() over (
        partition by reading_at, coalesce(transmitter_id, ''), glucose_raw
        order by source_file, source_row
    ) = 1

),

clarity as (

    select
        md5(concat_ws('|', epoch_ms(reading_at), coalesce(transmitter_id, ''), glucose_raw)) as reading_id,
        reading_at,
        local_wall                    as reading_at_local,
        cast(local_wall as date)      as reading_date,
        is_ambiguous                  as local_time_ambiguous,
        local_time_invalid,
        glucose_mmol,
        glucose_raw,
        censored,
        transmitter_id,
        source_device_id,
        source_file,
        'clarity'                     as data_source
    from deduplicated

)

select * from clarity
