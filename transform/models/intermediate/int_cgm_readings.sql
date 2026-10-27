-- All glucose readings, one row each, from both sources.
--
-- Clarity is the complete record (it includes readings the receiver backfilled after signal
-- loss). Share is used only after the last Clarity reading: the two sources timestamp and
-- round the same reading differently, so letting both cover the same period would count
-- readings twice. The column `data_source` says where each reading comes from.

with clarity as (

    select * from {{ ref('stg_clarity_readings') }}

),

clarity_end as (

    select coalesce(max(reading_at), '-infinity'::timestamptz) as last_reading_at
    from clarity

),

share as (

    select s.*
    from {{ ref('stg_share_readings') }} as s
    cross join clarity_end as c
    where s.reading_at > c.last_reading_at

)

select * from clarity
union all
select * from share
