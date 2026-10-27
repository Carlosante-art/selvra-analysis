-- One row per logged event. Self-reported: epistemically "self_reported" in Selvra terms.
-- A single-day event has end_date = start_date.

select
    md5(concat_ws('|', source_line, start, typ))       as event_id,
    cast(start as timestamp)                           as start_at,
    length(start) > 10                                 as has_time,
    cast(cast(start as timestamp) as date)             as start_date,
    coalesce(cast(cast(nullif(slut, '') as timestamp) as date),
             cast(cast(start as timestamp) as date))   as end_date,
    typ                                                as event_type,
    nullif(notering, '')                               as note,
    source_line
from {{ source('raw', 'personal_events') }}
