-- All glucose readings, one row each, from both sources.
--
-- Clarity is the complete record (it includes readings the receiver backfilled after signal
-- loss). Share is used only after the last Clarity reading: the two sources timestamp and
-- round the same reading differently, so letting both cover the same period would count
-- readings twice. The column `source` says where each reading comes from.

with clarity as (

    select * from {{ ref('stg_clarity_readings') }}

),

share as (

    select * from {{ ref('stg_share_readings') }}
    where reading_at > coalesce((select max(reading_at) from clarity), '-infinity'::timestamptz)

)

select * from clarity
union all
select * from share
