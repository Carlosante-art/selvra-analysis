-- Every distinct reading in the raw exports must survive to the flagged layer.
-- Flagging is allowed; dropping is not.
with raw_distinct as (
    select count(distinct ts_raw || '|' || transmitter_id || '|' || glucose_raw) as n
    from {{ source('raw', 'clarity_events') }}
    where event_type = 'EGV' and ts_raw <> ''
),
flagged as (
    select count(*) as n from {{ ref('int_cgm_flagged') }}
)
select raw_distinct.n as raw_n, flagged.n as flagged_n
from raw_distinct, flagged
where raw_distinct.n <> flagged.n
