-- Patient identifiers must never reach the database.
select event_type
from {{ source('clarity', 'clarity_events') }}
where event_type in ('FirstName', 'LastName', 'DateOfBirth')
