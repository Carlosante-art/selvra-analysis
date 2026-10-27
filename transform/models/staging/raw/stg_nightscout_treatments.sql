-- Nightscout treatments: bolus insulin, carbs and temp basals as the user's
-- pump, loop or manual entry recorded them. Nightscout stores manual entries
-- and pump records identically; the engine cannot tell them apart.

{% set tz = var('local_timezone') %}

select
    t.treatment_at,
    timezone('{{ tz }}', t.treatment_at)                 as treatment_at_local,
    cast(timezone('{{ tz }}', t.treatment_at) as date)   as treatment_date,
    t.event_type,
    t.insulin_units,
    t.carbs_g,
    t.duration_min,
    t.basal_rate
from {{ source('raw', 'nightscout_treatments') }} as t
where t.treatment_at is not null
