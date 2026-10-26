-- An event cannot end before it starts. Usually a typo in the log.
select event_id, start_date, end_date, source_line
from {{ ref('stg_personal_events') }}
where end_date < start_date
