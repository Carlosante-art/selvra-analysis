-- Nightscout sgv readings: the DIY community's own server. Exact UTC instants,
-- mg/dL, converted with 18.016. Out-of-range handled like Share: below 40 and
-- above 400 are treated as Low/High at the sensor limits.

{% set tz = var('local_timezone') %}

select
    md5(concat_ws('|', 'nightscout', epoch_ms(n.reading_at)))           as reading_id,
    n.reading_at,
    timezone('{{ tz }}', n.reading_at)                                  as reading_at_local,
    cast(timezone('{{ tz }}', n.reading_at) as date)                    as reading_date,
    false                                                               as local_time_ambiguous,
    false                                                               as local_time_invalid,
    round(case
        when n.value_mgdl < 40  then {{ var('sensor_low_mmol') }}
        when n.value_mgdl > 400 then {{ var('sensor_high_mmol') }}
        else n.value_mgdl / 18.016
    end, 1)                                                             as glucose_mmol,
    cast(n.value_mgdl as varchar)                                       as glucose_raw,
    case when n.value_mgdl < 40 then 'low' when n.value_mgdl > 400 then 'high' end as censored,
    cast(null as varchar)                                               as transmitter_id,
    n.device                                                            as source_device_id,
    'nightscout'                                                        as source_file,
    'nightscout'                                                        as data_source
from {{ source('raw', 'nightscout_entries') }} as n
