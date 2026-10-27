-- One row per calendar day (local time). Standard CGM metrics per the international
-- consensus (Battelino et al., Diabetes Care 2019), computed on all readings and on
-- readings without artefact flags. Days below the coverage threshold are kept but marked.

with readings as (

    select
        *,
        flag_compression_low or flag_implausible_jump as is_artefact
    from {{ ref('int_cgm_flagged') }}

),

daily as (

    select
        reading_date,
        count(*)                                                        as n_readings,
        count(*) filter (where is_artefact)                             as n_artefact,
        count(*) filter (where flag_compression_low)                    as n_compression_low,
        count(*) filter (where flag_early_sensor)                       as n_early_sensor,
        count(*) filter (where flag_censored)                           as n_censored,

        avg(glucose_mmol)                                               as mean_mmol,
        stddev_samp(glucose_mmol)                                       as sd_mmol,

        avg(case when glucose_mmol between {{ var('range_low_mmol') }} and {{ var('range_high_mmol') }} then 100.0 else 0 end) as tir_pct,
        avg(case when glucose_mmol >  {{ var('range_high_mmol') }}  then 100.0 else 0 end) as tar_pct,
        avg(case when glucose_mmol >  {{ var('level2_high_mmol') }} then 100.0 else 0 end) as tar_level2_pct,
        avg(case when glucose_mmol <  {{ var('range_low_mmol') }}   then 100.0 else 0 end) as tbr_pct,
        avg(case when glucose_mmol <  {{ var('level2_low_mmol') }}  then 100.0 else 0 end) as tbr_level2_pct,

        avg(glucose_mmol) filter (where not is_artefact)                as mean_mmol_clean,
        avg(case when glucose_mmol between {{ var('range_low_mmol') }} and {{ var('range_high_mmol') }} then 100.0 else 0 end)
            filter (where not is_artefact)                              as tir_pct_clean,
        avg(case when glucose_mmol < {{ var('range_low_mmol') }} then 100.0 else 0 end)
            filter (where not is_artefact)                              as tbr_pct_clean
    from readings
    group by reading_date

),

-- Consensus 2023 glycaemic events, counted on the local date they start.
-- The _clean counts leave out events that contain a flagged artefact.
events as (

    select
        start_date as reading_date,
        count(*) filter (where event_type = 'hypo_level1')                              as n_hypo_level1_events,
        count(*) filter (where event_type = 'hypo_level2')                              as n_hypo_level2_events,
        count(*) filter (where event_type = 'hypo_extended')                            as n_hypo_extended_events,
        count(*) filter (where event_type = 'hyper_level1')                             as n_hyper_level1_events,
        count(*) filter (where event_type = 'hyper_level2')                             as n_hyper_level2_events,
        count(*) filter (where event_type = 'hypo_level1' and not contains_artefact)    as n_hypo_level1_events_clean,
        count(*) filter (where event_type = 'hypo_level2' and not contains_artefact)    as n_hypo_level2_events_clean
    from {{ ref('int_glycaemic_events') }}
    group by start_date

),

-- Expected readings follow the local day's real length: 23 h (276) in spring, 25 h (300) in autumn.
day_lengths as (

    select
        *,
        date_diff('minute',
            timezone('{{ var('local_timezone') }}', reading_date::timestamp),
            timezone('{{ var('local_timezone') }}', (reading_date + 1)::timestamp)) / 5 as n_expected
    from daily

)
,

joined as (

    select
        d.*,
        e.* exclude (reading_date)  -- noqa: RF02
    from day_lengths as d
    left join events as e on d.reading_date = e.reading_date

)

select
    reading_date,
    n_readings,
    n_expected,
    round(100.0 * n_readings / n_expected, 1)                         as coverage_pct,
    100.0 * n_readings / n_expected >= {{ var('valid_day_coverage_pct') }} as is_valid_day,
    n_artefact,
    n_compression_low,
    n_early_sensor,
    n_censored,
    round(mean_mmol, 2)                                                 as mean_mmol,
    round(sd_mmol, 2)                                                   as sd_mmol,
    round(100.0 * sd_mmol / mean_mmol, 1)                               as cv_pct,
    -- GMI (Bergenstal et al. 2018): 3.31 + 0.02392 x mean glucose in mg/dL
    round(3.31 + 0.02392 * mean_mmol * 18.016, 2)                       as gmi_pct,
    round(tir_pct, 1)                                                   as tir_pct,
    round(tar_pct, 1)                                                   as tar_pct,
    round(tar_level2_pct, 1)                                            as tar_level2_pct,
    round(tbr_pct, 1)                                                   as tbr_pct,
    round(tbr_level2_pct, 1)                                            as tbr_level2_pct,
    round(mean_mmol_clean, 2)                                           as mean_mmol_clean,
    round(tir_pct_clean, 1)                                             as tir_pct_clean,
    round(tbr_pct_clean, 1)                                             as tbr_pct_clean,
    coalesce(n_hypo_level1_events, 0)                                   as n_hypo_level1_events,
    coalesce(n_hypo_level2_events, 0)                                   as n_hypo_level2_events,
    coalesce(n_hypo_extended_events, 0)                                 as n_hypo_extended_events,
    coalesce(n_hyper_level1_events, 0)                                  as n_hyper_level1_events,
    coalesce(n_hyper_level2_events, 0)                                  as n_hyper_level2_events,
    coalesce(n_hypo_level1_events_clean, 0)                             as n_hypo_level1_events_clean,
    coalesce(n_hypo_level2_events_clean, 0)                             as n_hypo_level2_events_clean
from joined
order by reading_date
