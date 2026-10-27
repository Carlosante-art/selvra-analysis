-- Every distinct reading in the raw exports must survive to the flagged layer.
-- Flagging is allowed; dropping is not. Share readings count from the last Clarity reading on.
--
-- Overlapping exports repeat readings across files; those are one reading. Within one file the
-- same (time, transmitter, value) can legitimately appear twice: in the autumn hour that occurs
-- twice. So a reading counts as many times as it appears in the file that has it most often.
with per_file as (
    select
        ts_raw,
        glucose_raw,
        source_file,
        coalesce(transmitter_id, '') as transmitter_id,
        count(*) as n
    from {{ source('raw', 'clarity_events') }}
    where event_type = 'EGV' and ts_raw <> ''
    group by all
),

per_reading as (
    select max(n) as n
    from per_file
    group by ts_raw, transmitter_id, glucose_raw
),

raw_distinct as (
    select coalesce(sum(n), 0) as n from per_reading
),

clarity_end as (
    select coalesce(max(reading_at), '-infinity'::timestamptz) as last_reading_at
    from {{ ref('stg_clarity_readings') }}
),

share_after_clarity as (
    select count(*) as n
    from {{ source('raw', 'share_readings') }} as s
    cross join clarity_end as c
    where s.reading_at > c.last_reading_at
),

flagged as (
    select count(*) as n from {{ ref('int_cgm_flagged') }}
)

select
    raw_distinct.n + share_after_clarity.n as raw_n,
    flagged.n as flagged_n
from raw_distinct
cross join share_after_clarity
cross join flagged
where raw_distinct.n + share_after_clarity.n <> flagged.n
