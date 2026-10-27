"""Design review before a study is locked: every check that can be computed, run on your own data.

The study-design agent (.claude/agents/studiedesigner.md) asks the questions that need a human;
this module answers the ones that need data, the same way every time. `las` refuses unless this
review has passed for exactly the version of the file being locked.

    uv run python -m selvra_analysis.granska studies/NNN-namn/studie.yml --db data/selvra.duckdb

Each check is OK, VARNING (lock allowed; say why in the study file) or STOPP (lock refused).
Sources for every threshold are in docs/studiedesign.md.

n1 checks
    struktur       the file states how adherence is measured and what kind of action A is
    tid            start in the future; calendar span short enough to avoid seasonal drift
    tidsordning    the negative control ends before A can act; the outcome window does not
    overforing     analysed days far enough apart for the action's carryover (Riddell 2017)
    positivitet    both conditions occurred, per day type, in your last 8 weeks (Daza 2018)
    underlag       expected valid pairs after data loss; smallest attainable p below alpha
    styrka         power from your own day-to-day variability on the eligible days
    apparat        the adherence measure comes from one device in the history
    data           the review ran on real data, not the synthetic demo

observation checks
    underlag       exposed and comparison days with a valid outcome, against minsta_underlag
    dagtyp         exposed and comparison days have a similar share of weekend days
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd

from selvra_analysis import n1
from selvra_analysis import study as st
from selvra_analysis.provenance import ROOT, data_version

OK, VARNING, STOPP = "OK", "VARNING", "STOPP"
HISTORY_DAYS = 56       # positivity: the last 8 weeks
SD_HISTORY_DAYS = 90    # variability and coverage: the last 90 days
MIN_STRATUM_DAYS = 7
MIN_SD_DAYS = 14
MIN_POWER = 0.80
MAX_PAIRS_SEARCHED = 60
MAX_SPAN_DAYS = 120
POWER_SIMS = 500
# Calendar days between two consecutive analysed days: (stop below, warn below, reason).
CARRYOVER = {
    "traning": (2, 3, ("insulinkänsligheten är förhöjd upp till 24–48 h efter träning och "
                       "hypoglykemirisken minst 24 h, nattlig risk störst efter eftermiddagsträning (Riddell 2017)")),
    "alkohol": (2, 2, "alkohol ger fördröjd hypoglykemi morgonen efter, 07–11 (White 2017)"),
    "somn": (1, 2, "en kort natt sänker insulinkänsligheten dagen efter (Donga 2010)"),
    "maltid": (1, 1, ""),
    "annat": (1, 1, ""),
}
WEEKEND = {5, 6}
DAYTYPE_WARN = 0.25   # observation: difference in weekend share between exposed and comparison days
DAYTYPE_STOP = 0.50


@dataclass
class Check:
    id: str
    level: str
    text: str


def _verdict(checks: list[Check]) -> str:
    levels = {c.level for c in checks}
    return STOPP if STOPP in levels else VARNING if VARNING in levels else OK


# --- Data helpers ------------------------------------------------------------------------------

def _columns(con) -> set[str]:
    return {r[0] for r in con.execute(
        "select column_name from information_schema.columns "
        "where table_schema = 'marts' and table_name = 'mart_analysis_days'").fetchall()}


def _recent(df: pd.DataFrame, days: int, column: str = "reading_date") -> pd.DataFrame:
    """The last `days` calendar days of the data, as a frame with a date column."""
    df = df.copy()
    df[column] = pd.to_datetime(df[column]).dt.date
    if df.empty:
        return df
    end = df[column].max()
    return df[df[column] > end - timedelta(days=days)]


Stratum = tuple[str, Callable[[date], bool]]


def _workdays(con) -> set[date] | None:
    """Days with a logged work shift in the recent history, or None if no shifts are logged.

    With a rotating schedule the weekday says nothing about whether a day was a work day;
    the event log (type `arbete`, e.g. imported from the roster calendar) does.
    """
    if "is_workday" not in _columns(con):
        return None
    df = _recent(con.execute("select reading_date, is_workday from marts.mart_analysis_days").df(), SD_HISTORY_DAYS)
    days = set(df.loc[df["is_workday"] == True, "reading_date"])
    return days or None


def _strata(design: dict, workdays: set[date] | None) -> tuple[list[Stratum], str | None]:
    """Day types to check, as (name, predicate on a date), and a caveat when the history is a proxy."""
    days = design.get("dagar") or {}
    if days.get("veckodagar"):
        wd = {n1.WEEKDAYS[w] for w in days["veckodagar"]}
        if workdays:
            # A rotating roster can make an allowed weekday a work day every other week.
            return [("tillåtna veckodagar med arbetspass", lambda x: x.weekday() in wd and x in workdays),
                    ("tillåtna veckodagar utan arbetspass", lambda x: x.weekday() in wd and x not in workdays)], None
        return [("de tillåtna veckodagarna", lambda x: x.weekday() in wd)], None
    if days.get("datum"):
        if workdays:
            return [("lediga dagar enligt händelseloggen", lambda x: x not in workdays)], (
                "en dag utan loggat arbetspass räknas som ledig; logga alla pass (make import-kalender)")
        wd = {x.weekday() for x in days["datum"]}
        return [("samma veckodagar som de valda datumen", lambda x: x.weekday() in wd)], (
            "dagarna är en datumlista men inga arbetspass är loggade, så historiken approximeras med "
            "veckodagar; vid rullande schema blandar det lediga dagar och arbetsdagar. Logga passen "
            "(typ arbete, t.ex. make import-kalender) och granska igen")
    if workdays:
        return [("arbetsdagar", lambda x: x in workdays), ("lediga dagar", lambda x: x not in workdays)], None
    return [("vardagar", lambda x: x.weekday() < 5), ("helger", lambda x: x.weekday() in WEEKEND)], None


def _in_any(strata: list[Stratum], x: date) -> bool:
    return any(pred(x) for _, pred in strata)


def _analysed_dates(design: dict) -> list[date]:
    """Every analysed day of the study, in calendar order, before randomisation."""
    if "dagar" in design:
        return n1.eligible_dates(design["start"], 2 * design["par"], design["dagar"].get("veckodagar"),
                                 design["dagar"].get("datum"), design["dagar"].get("minsta_avstand", 1))
    sched = n1.make_schedule(design["start"], design["par"], design["periodlangd_dagar"],
                             design.get("tvatt_dagar", 0), seed=0)
    return list(sched.loc[~sched["washout"], "date"])


def _min_gap_between_periods(design: dict) -> int:
    """Fewest calendar days between the last analysed day of one period and the first of the next,
    which is where one condition's effect can leak into the other's outcome."""
    if "dagar" in design:
        days = _analysed_dates(design)
        return min((b - a).days for a, b in itertools.pairwise(days))
    return design.get("tvatt_dagar", 0) + 1


def _minutes(clock: str) -> int:
    h, m = clock.split(":")
    return int(h) * 60 + int(m)


# --- n1 checks ---------------------------------------------------------------------------------

def _check_structure(design: dict) -> list[Check]:
    out = []
    if "foljsamhet" not in design:
        out.append(Check("struktur", STOPP, "design.foljsamhet saknas: hur verifieras varje dags villkor ur data? "
                                            "(t.ex. {kolumn: steps, A: {min: 10000}, B: {max: 5000}}, eller "
                                            "{kolumn: manuell})"))
    elif design["foljsamhet"].get("kolumn") == "manuell":
        out.append(Check("struktur", VARNING, "följsamheten är självrapporterad (kolumn: manuell); den kan inte "
                                              "kontrolleras mot data och positiviteten kan inte prövas"))
    if "verkan" not in design:
        out.append(Check("struktur", STOPP, "design.verkan saknas: {typ: traning|alkohol|somn|maltid|annat, "
                                            "borjar: \"HH:MM\"} styr kontrollen av överföring och tidsordning"))
    return out


def _check_time(design: dict, today: date) -> list[Check]:
    days = _analysed_dates(design)
    span = (days[-1] - design["start"]).days + 1
    out = []
    if design["start"] <= today:
        out.append(Check("tid", STOPP, f"start {design['start']} är inte i framtiden; schemat måste lottas före "
                                       "första försöksdagen"))
    level = VARNING if span > MAX_SPAN_DAYS else OK
    out.append(Check("tid", level, f"{len(days)} analyserade dagar från {design['start']} till {days[-1]} "
                                   f"({span} kalenderdagar)" + (
                                       "; över fyra månader ger säsong, sensorbyten och formförändring tid att "
                                       "glida, paren balanserar bara långsam drift" if level == VARNING else "")))
    return out


def _check_order(spec: dict) -> list[Check]:
    start = _minutes(spec["design"]["verkan"]["borjar"])
    out = []
    neg = spec["negativ_kontroll"]
    if "fonster" in neg:
        end = _minutes(neg["fonster"][1])
        if end > start:
            out.append(Check("tidsordning", STOPP,
                             f"negativa kontrollen slutar {neg['fonster'][1]}, efter att A kan börja verka "
                             f"{spec['design']['verkan']['borjar']}; den kan då påverkas av A"))
        else:
            out.append(Check("tidsordning", OK, "negativa kontrollen ligger före A samma dag"))
    o = spec["utfall"]
    if "fonster" in o and _minutes(o["fonster"][1]) <= start:
        out.append(Check("tidsordning", STOPP, f"utfallsfönstret slutar {o['fonster'][1]}, innan A kan verka"))
    return out


def _check_carryover(spec: dict) -> list[Check]:
    d = spec["design"]
    kind = d["verkan"]["typ"]
    stop, warn, why = CARRYOVER[kind]
    gap = _min_gap_between_periods(d)
    night_control = "fonster" in spec["negativ_kontroll"] and _minutes(spec["negativ_kontroll"]["fonster"][0]) < 360
    tail = (" Den nattliga negativa kontrollen ligger då också i förra A-dagens eftereffekt och prövar inget."
            if night_control and gap < warn else "")
    text = f"minst {gap} kalenderdag(ar) mellan två analyserade dagar med olika villkor; {why or 'kort verkan'}."
    if gap < stop:
        return [Check("overforing", STOPP, text + f" Kräver minst {stop}, helst {warn}: lägg tvättdagar eller "
                                                  "välj tillåtna dagar som inte ligger intill varandra." + tail)]
    if gap < warn:
        return [Check("overforing", VARNING, text + f" Helst {warn}; redovisa AB mot BA." + tail)]
    return [Check("overforing", OK, text)]


def _check_positivity(spec: dict, con) -> list[Check]:
    d = spec["design"]
    f = d.get("foljsamhet") or {}
    col = f.get("kolumn")
    if not col or col == "manuell":
        return []
    if col not in _columns(con):
        return [Check("positivitet", STOPP, f"kolumnen {col!r} finns inte i marts.mart_analysis_days")]
    hist = _recent(con.execute(f'select reading_date, "{col}" as x from marts.mart_analysis_days').df(),  # noqa: S608
                   HISTORY_DAYS)
    hist = hist[hist["x"].notna()]
    if hist.empty:
        return [Check("positivitet", STOPP,
                      f"ingen mätning av {col} de senaste {HISTORY_DAYS} dagarna: varken positivitet eller "
                      "följsamhet går att verifiera. Ladda källan (Oura: OURA_TOKEN och make live) eller "
                      "ange kolumn: manuell och motivera")]
    out_source = _check_one_device(con, hist)
    workdays = _workdays(con)
    strata, caveat = _strata(d, workdays)
    rows, out = [], []
    if caveat and not workdays:
        out.append(Check("positivitet", VARNING, "dagstypen kan inte verifieras ur datan: " + caveat))
    justified = isinstance(d.get("genomforbarhet"), str) and d["genomforbarhet"].strip() != ""
    for name, pred in strata:
        x = hist.loc[hist["reading_date"].map(pred), "x"]
        row, checks = _stratum_positivity(name, x, f, justified, several=len(strata) > 1)
        rows.append(row)
        out += checks
    summary = Check("positivitet", OK, "historik per dagstyp: " + "; ".join(rows) +
                    (f" (OBS: {caveat})" if caveat else ""))
    return [summary, *out_source, *out]


def _stratum_positivity(name: str, x: pd.Series, f: dict, justified: bool, several: bool) -> tuple[str, list[Check]]:
    """Both conditions in one day type. Only A, the deliberate intervention, can be justified
    when it never occurred: B is the ordinary day (F4), so a B that never happens on a day type
    means that day type does not belong in the study."""
    n = len(x)
    n_a = int(x.map(lambda v: st.meets(float(v), f["A"])).sum())
    n_b = int(x.map(lambda v: st.meets(float(v), f["B"])).sum())
    row = f"{name}: {n} dagar, A uppfyllt {n_a}, B uppfyllt {n_b}, median {x.median():.0f}" if n else \
        f"{name}: inga dagar med mätning"
    if n == 0 and several:
        return row, []
    if n < MIN_STRATUM_DAYS:
        return row, [Check("positivitet", VARNING, f"{name}: bara {n} dagar med mätning; för lite för att bedöma")]
    out = []
    for cond, k in (("A", n_a), ("B", n_b)):
        if k == 0:
            excused = justified and cond == "A"
            out.append(Check("positivitet", VARNING if excused else STOPP,
                             f"{cond} inträffade inte en enda gång på {name} under {HISTORY_DAYS} dagar. " + (
                                 "Motiverat i design.genomforbarhet." if excused else
                                 "B är den vanliga dagen och går inte att skapa med en motivering: begränsa "
                                 "design.dagar till dagar där den förekommer." if cond == "B" else
                                 "Antingen är villkoret omöjligt där (begränsa design.dagar eller definiera om "
                                 "villkoret relativt dagstypen) eller så ska design.genomforbarhet förklara hur "
                                 "det ska gå till.")))
        elif k >= 0.8 * n:
            other = "B" if cond == "A" else "A"
            out.append(Check("positivitet", VARNING,
                             f"{name}: {cond} är det vanliga ({k} av {n} dagar), så kontrasten skapas helt av att "
                             f"du aktivt gör {other}; säkerställ att {other} går att hålla och är säkert"))
    return row, out


def _check_one_device(con, hist: pd.DataFrame) -> list[Check]:
    """Oura and Garmin count steps differently; a series that switches device mid-way is two measures."""
    if "wearable_source" not in _columns(con):
        return []
    src = _recent(con.execute("select reading_date, wearable_source from marts.mart_analysis_days "
                              "where wearable_source is not null").df(), HISTORY_DAYS)
    src = src[src["reading_date"].isin(set(hist["reading_date"]))]
    counts = src["wearable_source"].value_counts().to_dict()
    if len(counts) > 1:
        return [Check("apparat", VARNING,
                      f"mätningen kommer från flera apparater de senaste {HISTORY_DAYS} dagarna {counts}; "
                      "använd en apparat under hela studien och skriv vilken i design.foljsamhet")]
    return []


def _expected_valid_pairs(pairs: int, valid_rate: float, analysed_days: int) -> int:
    period_ok = 1 - (1 - valid_rate) ** analysed_days
    return math.floor(pairs * period_ok ** 2)


def _pair_q(rate: float, analysed: int) -> float:
    """Probability that one pair completes: both periods deliver a valid outcome."""
    return (1 - (1 - rate) ** analysed) ** 2


def _expected_power(pairs: int, q: float, effect: float, sd: float, alpha: float,
                    cache: dict) -> float:
    """Power averaged over the binomial distribution of complete pairs, not at its floor.

    Flooring the expectation cost ~10 percentage points at the boundary (benchmark dold2:
    d05 stopped at "71%" where the true power was 90%). The distribution is the honest view."""
    if q >= 0.999:
        fordelning = {pairs: 1.0}
    else:
        fordelning = {k: math.comb(pairs, k) * q ** k * (1 - q) ** (pairs - k)
                      for k in range(pairs + 1)}
        fordelning = {k: pm for k, pm in fordelning.items() if pm >= 0.005}
        tot_p = sum(fordelning.values())
        fordelning = {k: pm / tot_p for k, pm in fordelning.items()}
    pw = 0.0
    for k, pm in fordelning.items():
        if k < 1 or 2 / 2 ** k > alpha:
            continue
        nyckel = (k, round(sd, 6))
        if nyckel not in cache:
            cache[nyckel] = n1.power(k, effect, sd, alpha, n_sim=POWER_SIMS)
        pw += pm * cache[nyckel]
    return pw


def _pairs_needed(pairs: int, q: float, effect: float, sd: float, alpha: float,
                  cache: dict) -> int | None:
    """Fewest pairs with expected power >= MIN_POWER, by bisection (power rises with pairs)."""
    def enough(n: int) -> bool:
        return _expected_power(n, q, effect, sd, alpha, cache) >= MIN_POWER
    lo, hi = pairs, MAX_PAIRS_SEARCHED
    if not enough(hi):
        return None
    while hi - lo > 1:
        mid = (lo + hi) // 2
        lo, hi = (lo, mid) if enough(mid) else (mid, hi)
    return hi


def _check_power(study: st.Study, con) -> list[Check]:
    spec, d = study.spec, study.design
    alpha = 1 - spec["analys"].get("niva", 0.95)
    pairs = d["par"]
    analysed = d["periodlangd_dagar"] - d.get("tvatt_dagar", 0)
    out = []
    p_min = 2 / 2 ** pairs
    if p_min > alpha:
        out.append(Check("underlag", STOPP, f"{pairs} par ger minsta möjliga p {p_min:.4f}, över {alpha:.2f}"))
    daily, col = st._daily_outcome(study, con)
    daily = _recent(daily, SD_HISTORY_DAYS)
    if daily.empty:
        return [*out, Check("styrka", STOPP, "ingen glukoshistorik att skatta variationen från")]
    strata, _ = _strata(d, _workdays(con))
    end = daily["reading_date"].max()
    in_stratum = daily[daily["reading_date"].map(lambda x: _in_any(strata, x))]
    valid = in_stratum[st.utfallsgiltig(in_stratum, col)][col].dropna()
    # Data loss is a property of the sensor and the routine, not of the day type, so it is
    # estimated on every day of the history; one weekday gives too few days to estimate it.
    span = (end - daily["reading_date"].min()).days + 1
    rate = len(daily[st.utfallsgiltig(daily, col)][col].dropna()) / span
    k_eff = _expected_valid_pairs(pairs, rate, analysed)
    out.append(Check("underlag", VARNING if rate < 0.8 else OK,
                     f"{rate:.0%} av de tillåtna dagarna de senaste {SD_HISTORY_DAYS} dagarna hade giltigt utfall; "
                     f"väntat antal kompletta par {k_eff} av {pairs}"))
    if k_eff < 1 or 2 / 2 ** k_eff > alpha:
        out.append(Check("underlag", STOPP, f"med väntat bortfall ({k_eff} par) kan testet inte nå p ≤ {alpha:.2f}; "
                                            "öka design.par"))
        return out
    basis = "tillåtna dagar"
    if len(valid) < MIN_SD_DAYS:
        # Too few eligible days of history (one weekday gives 13 in 90 days): pool all days —
        # but within day type. A study comparing Saturdays with Saturdays should not count the
        # workday/day-off level difference as noise (benchmark f18/j08: pooled 1.8 vs true 0.9).
        alla = daily[st.utfallsgiltig(daily, col)][["reading_date", col]].dropna(subset=[col])
        valid = alla[col]
        basis = "alla dagar, för få tillåtna"
        if len(valid) < MIN_SD_DAYS:
            out.append(Check("styrka", VARNING, f"bara {len(valid)} giltiga dagar att skatta variationen från; "
                                                "styrkan kan inte bedömas"))
            return out
        pass_dagar = _workdays(con)
        dagtyp = (alla["reading_date"].map(lambda x: x in pass_dagar)
                  if pass_dagar is not None else None)
        grupper = alla.groupby(dagtyp)[col] if dagtyp is not None else None
        if grupper is not None and grupper.ngroups > 1 and int(grupper.size().min()) >= 2:
            valid = alla[col] - grupper.transform("mean")
            basis = "alla dagar, inom dagstyp"
            out.append(Check("styrka", VARNING,
                             "variationen skattas på alla dagar eftersom de tillåtna är för få — inom "
                             "dagstyp (arbetsdag/ledig ur loggade pass), så nivåskillnaden mellan "
                             "dagstyperna räknas inte som brus"))
        else:
            out.append(Check("styrka", VARNING, "variationen skattas på alla dagar eftersom de tillåtna är för få; "
                                                "skiljer sig dagstyperna åt i variation blir styrkan fel"))
    sd = float(valid.std(ddof=1)) if analysed == 1 else n1.period_sd(daily, col, analysed)
    effect = abs(spec["analys"]["minsta_relevanta_effekt"])
    q = _pair_q(rate, analysed)
    cache: dict = {}
    pw = _expected_power(pairs, q, effect, sd, alpha, cache)
    text = (f"periodens SD {sd:.2f} (egen data, {basis}); väntad styrka {pw:.0%} att upptäcka "
            f"{effect:g} med {pairs} par, bortfallet inräknat som fördelning")
    if pw >= MIN_POWER:
        return [*out, Check("styrka", OK, text)]
    need = _pairs_needed(pairs, q, effect, sd, alpha, cache)
    advice = (f"; ungefär {need} par behövs" if need else
              f"; inte ens {MAX_PAIRS_SEARCHED} par räcker: välj ett utfall närmare mekanismen (kortare fönster) "
              "eller gör studien till en skattning och säg det i tesen")
    # SD skattad på få dagar är inte exakt. Rymmer osäkerheten 80 % är ett stopp inte
    # motiverat — det är ett gränsfall, och det ska sägas som varning med rådet kvar.
    n_sd = len(valid)
    sd_lo = sd * max(1 - 1.645 / math.sqrt(2 * max(n_sd - 1, 1)), 0.5)
    pw_hi = _expected_power(pairs, q, effect, sd_lo, alpha, cache)
    if pw_hi >= MIN_POWER:
        return [*out, Check("styrka", VARNING,
                            text + f". SD bygger på {n_sd} dagar; inom skattningens osäkerhet ryms "
                                   f"{MIN_POWER:.0%} (upp till {pw_hi:.0%}) — gränsfall" + advice
                                   + " för marginal")]
    return [*out, Check("styrka", STOPP, text + advice)]


def _check_data(con) -> list[Check]:
    if data_version(con)["synthetic"]:
        return [Check("data", STOPP, "granskningen kördes på syntetisk demodata; siffrorna säger inget om dig. "
                                     "Kör mot data/selvra.duckdb")]
    return []


# --- observation checks ------------------------------------------------------------------------

def _daytype_gap(day_is_work: pd.Series, exposed: pd.Series) -> float | None:
    work = day_is_work.reindex(exposed.index).astype(float)
    if not exposed.any() or exposed.all():
        return None
    return abs(work[exposed].mean() - work[~exposed].mean())


def _check_daytype(study: st.Study, con, s: pd.DataFrame) -> list[Check]:
    """Do exposed and comparison days differ in day type?

    Day type is work or off from logged shifts when there are any (a rotating roster makes the
    weekday meaningless), otherwise weekday or weekend. It is checked on the analysed day and
    on the exposure day, which differ when the outcome is the day after: high steps on work
    days confound the night after even if the night itself falls on any weekday.
    """
    valid = s[s["y"].notna() & s["exposed"].notna()]
    exposed = valid["exposed"].astype(bool)
    workdays = _workdays(con)
    if workdays:
        def is_work(idx: pd.Index) -> pd.Series:
            return pd.Series([x.date() in workdays for x in idx], index=idx)
        label = "andel arbetsdagar"
    else:
        def is_work(idx: pd.Index) -> pd.Series:
            return pd.Series(idx.day_of_week < 5, index=idx)
        label = "andel vardagar"
    lag = study.design["exponering"].get("dagar_efter", 0)
    gaps = {"den analyserade dagen": _daytype_gap(is_work(valid.index), exposed)}
    if lag:
        shifted = valid.index - pd.Timedelta(days=lag)
        gaps["exponeringsdagen"] = _daytype_gap(pd.Series(is_work(shifted).to_numpy(), index=valid.index), exposed)
    gaps = {k: v for k, v in gaps.items() if v is not None}
    if not gaps:
        return []
    where, gap = max(gaps.items(), key=lambda kv: kv[1])
    level = STOPP if gap > DAYTYPE_STOP else VARNING if gap > DAYTYPE_WARN else OK
    advice = {STOPP: "; exponeringen följer dagstypen och skillnaden går inte att skilja från arbetsdag mot ledig. "
                     "Jämför inom dagstyp eller gör ett lottat n1-försök med design.dagar",
              VARNING: "; dagstypen kan förklara skillnaden, jämför inom dagstyp", OK: ""}[level]
    return [Check("dagtyp", level, f"{label} på {where} skiljer {gap:.0%} mellan exponerade och "
                                   f"jämförelsedagar{advice}")]


def _check_observation(study: st.Study, con) -> list[Check]:
    daily, col = st._daily_outcome(study, con)
    s = st._observation_series(study, daily, col)
    n_exp, n_cmp = st._observation_counts(s)
    floor = study.spec["analys"].get("minsta_underlag", {})
    out = []
    short = n_exp < floor.get("exponerade", st.MIN_DAYS) or n_cmp < floor.get("jamforelse", st.MIN_DAYS)
    retro = study.design.get("retrospektiv", False)
    out.append(Check("underlag", STOPP if short and retro else VARNING if short else OK,
                     f"{n_exp} exponerade och {n_cmp} jämförelsedagar med giltigt utfall nu; "
                     f"studien kräver {floor.get('exponerade')} och {floor.get('jamforelse')}"
                     + (" och datan finns redan, så den kommer att vägras" if short and retro else "")))
    out += _check_daytype(study, con, s)
    return out


# --- Review ------------------------------------------------------------------------------------

def review(study: st.Study, con, today: date | None = None) -> dict:
    today = today or date.today()
    spec, d = study.spec, study.design
    checks = _check_data(con)
    if study.kind == "n1":
        checks += _check_structure(d)
        checks += _check_time(d, today)
        if "verkan" in d:
            checks += _check_order(spec)
            checks += _check_carryover(spec)
        checks += _check_positivity(spec, con)
        checks += _check_power(study, con)
    else:
        checks += _check_observation(study, con)
    return {
        "study": spec["id"],
        "reviewed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "spec_sha256": st._sha(study.path),
        "data_fingerprint": data_version(con)["fingerprint"],
        "verdict": _verdict(checks),
        "checks": [asdict(c) for c in checks],
    }


def render(result: dict) -> str:
    lines = [f"Designgranskning {result['study']}: {result['verdict']}", ""]
    lines += [f"  {c['level']:<7} {c['id']:<12} {c['text']}" for c in result["checks"]]
    if result["verdict"] == STOPP:
        lines += ["", "Låsning vägras tills alla STOPP är åtgärdade i studiefilen."]
    elif result["verdict"] == VARNING:
        lines += ["", "Låsning tillåten. Varje VARNING ska vara bemött i studiefilen (protokoll eller motivering)."]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("studie", type=Path)
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "selvra.duckdb")
    args = parser.parse_args(argv)
    try:
        study = st.load(args.studie.resolve())
        if study.lock_path.exists():
            raise st.StudyError("studien är redan låst; granskningen gäller utkast")
        with duckdb.connect(str(args.db), read_only=True) as con:
            result = review(study, con)
    except st.StudyError as err:
        print(f"Stopp: {err}", file=sys.stderr)
        return 2
    (study.folder / st.REVIEW_FILE).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(render(result))
    return 1 if result["verdict"] == STOPP else 0


if __name__ == "__main__":
    sys.exit(main())
