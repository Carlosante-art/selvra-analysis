-- Garmin-pass: en rad per startad aktivitet. Ett pass som aldrig startades
-- finns inte här — kolumnerna beskriver vad klockan fick veta, inget mer.

select
    activity_id,
    started_at,
    cast(started_at as date) as reading_date,
    activity_type,
    duration_s,
    distance_m,
    avg_hr
from {{ source('raw', 'garmin_activities') }}
where activity_id is not null
