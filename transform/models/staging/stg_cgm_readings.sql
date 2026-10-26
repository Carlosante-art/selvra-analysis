-- One row per glucose reading (EGV), typed, in mmol/L, deduplicated across overlapping exports.
-- Low/High are kept as censored values at the sensor limits, never dropped.

with source as (

    select * from {{ source('clarity', 'clarity_events') }}
    where event_type = 'EGV' and ts_raw <> ''

),

typed as (

    select
        strptime(ts_raw, '%Y-%m-%dT%H:%M:%S')                    as reading_at,
        glucose_raw,
        case glucose_raw when 'Low' then 'low' when 'High' then 'high' end as censored,
        case glucose_unit
            when 'mmol/L' then try_cast(replace(glucose_raw, ',', '.') as double)
            when 'mg/dL'  then try_cast(glucose_raw as double) / 18.016
        end                                                       as glucose_numeric,
        nullif(transmitter_id, '')                                as transmitter_id,
        nullif(source_device_id, '')                              as source_device_id,
        source_file
    from source

),

valued as (

    select
        *,
        round(case censored
            when 'low'  then {{ var('sensor_low_mmol') }}
            when 'high' then {{ var('sensor_high_mmol') }}
            else glucose_numeric
        end, 1) as glucose_mmol
    from typed

),

deduplicated as (

    select *
    from valued
    qualify row_number() over (
        partition by reading_at, coalesce(transmitter_id, ''), glucose_raw
        order by source_file
    ) = 1

)

select
    md5(concat_ws('|', reading_at, coalesce(transmitter_id, ''), glucose_raw)) as reading_id,
    reading_at,
    cast(reading_at as date) as reading_date,
    glucose_mmol,
    censored,
    transmitter_id,
    source_device_id,
    source_file
from deduplicated
