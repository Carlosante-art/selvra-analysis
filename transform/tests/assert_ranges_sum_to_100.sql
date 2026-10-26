-- Time below, in and above range must cover every reading exactly once.
select reading_date, tbr_pct + tir_pct + tar_pct as total
from {{ ref('fct_glucose_daily') }}
where abs(tbr_pct + tir_pct + tar_pct - 100) > 0.2
