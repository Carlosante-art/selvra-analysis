-- Glycaemic events per the international consensus for CGM in clinical trials
-- (Battelino et al., Lancet Diabetes Endocrinol 2023;11:42-57, Table 4).
--
--   hypo_level1      < 3.9 mmol/L for >= 15 consecutive min, ends after >= 15 min at >= 3.9
--   hypo_level2      < 3.0 mmol/L for >= 15 consecutive min, ends after >= 15 min at >= 3.0
--   hypo_extended    < 3.9 mmol/L for >  120 consecutive min, ends after >= 15 min at >= 3.9
--   hyper_level1     > 10.0 mmol/L for >= 15 consecutive min, ends after >= 15 min at <= 10.0
--   hyper_level2     > 13.9 mmol/L for >= 15 consecutive min, ends after >= 15 min at <= 13.9
--
-- "Consecutive minutes" are counted in readings (15 min = 3 readings at 5-minute intervals)
-- within a recording segment. A gap longer than var('segment_gap_minutes') ends the segment, and
-- an event still open at a segment's end ends with its last reading. Missing values are never
-- interpolated: the consensus does not specify interpolation, and an invented value could
-- start or end an event. The algorithm is iglu's episode_calculation event logic, checked
-- against iglu itself on the same readings (validation/iglu).
--
-- Epistemics: derived. Events are computed on all readings; contains_artefact marks events that
-- include a flagged reading (a suspected compression low is the usual cause of a false hypo event).

{% set step = var('cgm_interval_minutes') %}
{% set n_min = (var('event_min_minutes') / step) | round(0, 'ceil') | int %}
{% set n_end = (var('event_end_minutes') / step) | round(0, 'ceil') | int %}
{% set n_ext = (var('extended_hypo_minutes') / step) | int + 1 %}

{% set event_types = [
    ('hypo_level1',   'glucose_mmol < ' ~ var('range_low_mmol'),    n_min),
    ('hypo_level2',   'glucose_mmol < ' ~ var('level2_low_mmol'),   n_min),
    ('hypo_extended', 'glucose_mmol < ' ~ var('range_low_mmol'),    n_ext),
    ('hyper_level1',  'glucose_mmol > ' ~ var('range_high_mmol'),   n_min),
    ('hyper_level2',  'glucose_mmol > ' ~ var('level2_high_mmol'),  n_min),
] %}

with readings as (

    select
        *,
        flag_compression_low or flag_implausible_jump as is_artefact,
        row_number() over (partition by segment_id order by reading_at, reading_id) as rn,
        count(*) over (partition by segment_id)                                     as segment_n
    from {{ ref('int_cgm_flagged') }}

)

{% for name, condition, n_start in event_types %}
,

{{ name }}_marked as (

    select segment_id, rn, segment_n, {{ condition }} as beyond
    from readings

),

{{ name }}_runs as (

    select segment_id, beyond, min(rn) as run_start, count(*) as run_length, any_value(segment_n) as segment_n
    from (
        select *, rn - row_number() over (partition by segment_id, beyond order by rn) as run_key
        from {{ name }}_marked
    )
    group by segment_id, beyond, run_key

),

-- Each qualifying start ends just before the first qualifying return that follows it.
-- Starts that share an end belong to one event, which begins at the earliest of them.
{{ name }}_events as (

    select segment_id, min(start_rn) as start_rn, last_rn
    from (
        select
            s.segment_id,
            s.run_start as start_rn,
            coalesce(min(e.run_start), any_value(s.segment_n) + 1) - 1 as last_rn
        from {{ name }}_runs as s
        left join {{ name }}_runs as e
            on e.segment_id = s.segment_id
           and not e.beyond
           and e.run_length >= {{ n_end }}
           and e.run_start > s.run_start
        where s.beyond and s.run_length >= {{ n_start }}
        group by s.segment_id, s.run_start
    )
    group by segment_id, last_rn

)
{% endfor %}

, all_events as (

{% for name, condition, n_start in event_types %}
    select '{{ name }}' as event_type, segment_id, start_rn, last_rn from {{ name }}_events
    {% if not loop.last %}union all{% endif %}
{% endfor %}

)

select
    md5(concat_ws('|', e.event_type, e.segment_id, e.start_rn))           as event_id,
    e.event_type,
    e.segment_id,
    e.start_rn,
    e.last_rn,
    min(r.reading_at)                                                      as start_at,
    max(r.reading_at)                                                      as end_at,
    arg_min(r.reading_date, r.reading_at)                                  as start_date,
    arg_min(r.reading_at_local, r.reading_at)                              as start_at_local,
    count(*)                                                               as n_readings,
    date_diff('second', min(r.reading_at), max(r.reading_at)) / 60.0       as span_minutes,
    min(r.glucose_mmol)                                                    as nadir_mmol,
    max(r.glucose_mmol)                                                    as peak_mmol,
    round(avg(r.glucose_mmol), 2)                                          as mean_mmol,
    bool_or(r.is_artefact)                                                 as contains_artefact
from all_events as e
join readings as r
    on r.segment_id = e.segment_id
   and r.rn between e.start_rn and e.last_rn
group by all
