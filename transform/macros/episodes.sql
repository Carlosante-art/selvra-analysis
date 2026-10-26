{#
  Episode tools. They take the episode definition as input; they never define one.
  What counts as "high", "ill" or "active" is decided in each analysis's pre-registration.
#}


{#
  consecutive_runs: runs of consecutive calendar days that meet a condition.

  A missing day (no row in `relation`) breaks a run, because nothing is known about it.
  Put validity requirements (e.g. is_valid_day) in the condition explicitly.

  Returns: run_id, start_date, end_date, n_days

  Example:
    {{ consecutive_runs(ref('mart_analysis_days'), 'reading_date', 'had_training and is_valid_day', min_length=3) }}
#}
{% macro consecutive_runs(relation, date_column, condition, min_length=1) %}
    with qualifying as (
        select distinct {{ date_column }} as d
        from {{ relation }}
        where {{ condition }}
    ),
    grouped as (
        select d, d - cast(row_number() over (order by d) as integer) as island
        from qualifying
    )
    select
        row_number() over (order by min(d)) as run_id,
        min(d)                              as start_date,
        max(d)                              as end_date,
        count(*)                            as n_days
    from grouped
    group by island
    having count(*) >= {{ min_length }}
{% endmacro %}


{#
  event_windows: the days around each run, joined to a day-level table.

  offset_day  +1 = first day after the run, +2 the second, ...
              -1 = last day before the run, -2 the one before, ...
  Day 0 (inside the run) is not produced.

  in_other_run is true when a window day falls inside another run. Those days are
  contaminated: decide in the pre-registration whether to exclude them.
  window_date has no matching day row (all day columns null) when there is no data.

  Example:
    {{ event_windows(
        runs=consecutive_runs(ref('mart_analysis_days'), 'reading_date', 'had_training', 3),
        days=ref('mart_analysis_days'),
        days_after=7, days_before=3) }}
#}
{% macro event_windows(runs, days, days_after=7, days_before=0, date_column='reading_date') %}
    with runs as (
        {{ runs }}
    ),
    offsets as (
        select unnest(range({{ -days_before }}, 0)) as offset_day
        union all
        select unnest(range(1, {{ days_after + 1 }}))
    ),
    windows as (
        select
            r.run_id,
            r.start_date as run_start_date,
            r.end_date   as run_end_date,
            r.n_days     as run_n_days,
            o.offset_day,
            case when o.offset_day > 0
                 then r.end_date + cast(o.offset_day as integer)
                 else r.start_date + cast(o.offset_day as integer)
            end          as window_date
        from runs as r
        cross join offsets as o
    )
    select
        w.*,
        exists (
            select 1 from runs as r2
            where r2.run_id <> w.run_id
              and w.window_date between r2.start_date and r2.end_date
        ) as in_other_run,
        d.*
    from windows as w
    left join {{ days }} as d
        on d.{{ date_column }} = w.window_date
{% endmacro %}
