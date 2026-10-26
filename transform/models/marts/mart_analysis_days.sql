-- The table analyses start from: one row per day, glucose metrics + context.

select
    g.*,
    c.* exclude (reading_date)
from {{ ref('fct_glucose_daily') }} as g
left join {{ ref('fct_day_context') }} as c using (reading_date)
