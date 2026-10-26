-- Synthetic demo data and real data must never share a database. Mixed, the demo's
-- history would be read as yours (and Share readings would start after its last day).
with clarity as (
    select
        count(*) filter (where source_device_id = 'SYNTHETIC')                       as n_synthetic,
        count(*) filter (where coalesce(source_device_id, '') <> 'SYNTHETIC')        as n_real
    from {{ source('raw', 'clarity_events') }}
    where event_type = 'EGV'
),
share as (
    select count(*) as n from {{ source('raw', 'share_readings') }}
)
select clarity.n_synthetic, clarity.n_real, share.n as n_share
from clarity, share
where clarity.n_synthetic > 0 and (clarity.n_real > 0 or share.n > 0)
