-- All glucose readings, one row each, from the configured sources.
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

),

-- Nightscout is an alternative live source for users without Share. One live
-- source at a time: if any Share readings exist, Share wins and Nightscout is
-- ignored, so the same instant can never be counted twice.
share_present as (

    select count(*) > 0 as has_share from share

),

nightscout as (

    select n.*
    from {{ ref('stg_nightscout_readings') }} as n
    cross join clarity_end as c
    cross join share_present as p
    where n.reading_at > c.last_reading_at and not p.has_share

)

select * from clarity
union all
select * from share
union all
select * from nightscout
