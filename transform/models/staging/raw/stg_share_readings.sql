-- Dexcom Share readings collected by Selvra Diabetes: exact UTC instants, mg/dL as Dexcom
-- measures them, converted with 18.016. Out-of-range: Dexcom reports 40-400 mg/dL; values
-- outside are treated as Low/High at the sensor limits. No transmitter ID, no backfill.

{% set tz = var('local_timezone') %}

select
    md5(concat_ws('|', 'share', epoch_ms(s.reading_at)))                as reading_id,
    s.reading_at,
    timezone('{{ tz }}', s.reading_at)                                  as reading_at_local,
    cast(timezone('{{ tz }}', s.reading_at) as date)                    as reading_date,
    false                                                               as local_time_ambiguous,
    false                                                               as local_time_invalid,
    round(case
        when s.value_mgdl < 40  then {{ var('sensor_low_mmol') }}
        when s.value_mgdl > 400 then {{ var('sensor_high_mmol') }}
        else s.value_mgdl / 18.016
    end, 1)                                                             as glucose_mmol,
    cast(s.value_mgdl as varchar)                                       as glucose_raw,
    case when s.value_mgdl < 40 then 'low' when s.value_mgdl > 400 then 'high' end as censored,
    cast(null as varchar)                                               as transmitter_id,
    cast(null as varchar)                                               as source_device_id,
    'dexcom_share'                                                      as source_file,
    'dexcom_share'                                                      as data_source
from {{ source('raw', 'share_readings') }} as s
