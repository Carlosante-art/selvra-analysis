-- Known input, known answer. Days 1-3 qualify, day 4 does not, day 5 is missing (no data),
-- days 6-9 qualify. With min_length 3 that gives two runs: Jan 1-3 and Jan 6-9.
-- The run Jan 1-3 has day +3 (Jan 6) inside the other run, and day +2 (Jan 5) without data.

{% set days %}
    (select * from (values
        (date '2025-01-01', true),
        (date '2025-01-02', true),
        (date '2025-01-03', true),
        (date '2025-01-04', false),
        (date '2025-01-06', true),
        (date '2025-01-07', true),
        (date '2025-01-08', true),
        (date '2025-01-09', true),
        (date '2025-01-10', false),
        (date '2025-01-11', false)
    ) as t(reading_date, flag))
{% endset %}

with runs as (
    {{ consecutive_runs(days, 'reading_date', 'flag', min_length=3) }}
),

windows as (
    {{ event_windows(consecutive_runs(days, 'reading_date', 'flag', min_length=3), days, days_after=3, days_before=1) }}
),

checks as (
    select 'two runs' as check_name,
           (select count(*) from runs) = 2 as ok
    union all
    select 'first run Jan 1-3, 3 days',
           exists (select 1 from runs where start_date = date '2025-01-01' and end_date = date '2025-01-03' and n_days = 3)
    union all
    select 'second run Jan 6-9, 4 days',
           exists (select 1 from runs where start_date = date '2025-01-06' and end_date = date '2025-01-09' and n_days = 4)
    union all
    select 'four window rows per run',
           (select count(*) from windows) = 8
    union all
    select 'day +1 after first run is Jan 4',
           exists (select 1 from windows where run_id = 1 and offset_day = 1 and window_date = date '2025-01-04')
    union all
    select 'day +2 after first run has no data',
           exists (select 1 from windows where run_id = 1 and offset_day = 2 and reading_date is null)
    union all
    select 'day +3 after first run is inside the other run',
           exists (select 1 from windows where run_id = 1 and offset_day = 3 and in_other_run)
    union all
    select 'day -1 before second run is Jan 5',
           exists (select 1 from windows where run_id = 2 and offset_day = -1 and window_date = date '2025-01-05')
)

select check_name from checks where not ok
