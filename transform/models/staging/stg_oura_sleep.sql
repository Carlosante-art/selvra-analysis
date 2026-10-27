-- Staging: Oura sleep och readiness per dygn.
-- Tabellen skapas bara om OURA_TOKEN är satt och ingest_oura körs.
-- Om tabellen saknas returnerar denna vy en tom tabell — pipelinen håller.

{% if execute %}
  {% set has_oura = adapter.get_relation(database=none, schema='raw', identifier='oura_sleep') is not none %}
{% else %}
  {% set has_oura = false %}
{% endif %}

{% if has_oura %}
select
    cast(reading_date as date)  as reading_date,
    cast(sleep_score as integer)            as sleep_score,
    cast(readiness_score as integer)        as readiness_score,
    cast(hrv_avg as double)                 as hrv_avg,
    cast(hr_lowest as double)               as hr_lowest_bpm,
    cast(total_sleep_seconds as integer)    as total_sleep_seconds,
    cast(deep_sleep_seconds as integer)     as deep_sleep_seconds,
    cast(rem_sleep_seconds as integer)      as rem_sleep_seconds,
    cast(efficiency as double)              as sleep_efficiency_pct
from raw.oura_sleep
where reading_date is not null
{% else %}
select
    cast(null as date)      as reading_date,
    cast(null as integer)   as sleep_score,
    cast(null as integer)   as readiness_score,
    cast(null as double)    as hrv_avg,
    cast(null as double)    as hr_lowest_bpm,
    cast(null as integer)   as total_sleep_seconds,
    cast(null as integer)   as deep_sleep_seconds,
    cast(null as integer)   as rem_sleep_seconds,
    cast(null as double)    as sleep_efficiency_pct
where false
{% endif %}
