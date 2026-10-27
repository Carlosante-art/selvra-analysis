-- The table analyses start from: one row per day, glucose metrics + context.

-- The context carries the spine (every day with any data); glucose metrics are
-- null on wearable-only days. Column order preserved for the enforced contract.
select
    c.reading_date,
    g.* exclude (reading_date),
    c.* exclude (reading_date)
from {{ ref('fct_day_context') }} as c
left join {{ ref('fct_glucose_daily') }} as g using (reading_date)
