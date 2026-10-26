-- Every distinct reading in the raw exports must survive to the flagged layer.
-- Flagging is allowed; dropping is not. Share readings count from the last Clarity reading on.
--
-- Overlapping exports repeat readings across files; those are one reading. Within one file the
-- same (time, transmitter, value) can legitimately appear twice: in the autumn hour that occurs
-- twice. So a reading counts as many times as it appears in the file that has it most often.
with per_file as (
    select ts_raw, coalesce(transmitter_id, '') as transmitter_id, glucose_raw, source_file,
           count(*) as n
    from {{ source('raw', 'clarity_events') }}
    where event_type = 'EGV' and ts_raw <> ''
    group by all
),
raw_distinct as (
    select sum(n) as n
    from (select max(n) as n from per_file group by ts_raw, transmitter_id, glucose_raw)
),
share_after_clarity as (
    select count(*) as n
    from {{ source('raw', 'share_readings') }}
    where reading_at > coalesce(
        (select max(reading_at) from {{ ref('stg_cgm_readings') }} where source = 'clarity'),
        '-infinity'::timestamptz)
),
flagged as (
    select count(*) as n from {{ ref('int_cgm_flagged') }}
)
select coalesce(raw_distinct.n, 0) + share_after_clarity.n as raw_n, flagged.n as flagged_n
from raw_distinct, share_after_clarity, flagged
where coalesce(raw_distinct.n, 0) + share_after_clarity.n <> flagged.n
