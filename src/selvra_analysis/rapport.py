"""Slutrapporten: spec + körjournal → läsbar text. Ren lövmodul utan motorberoenden.

Varje tal i rapporten kommer ur körjournalen (record) eller den låsta specen —
aldrig ur en ny beräkning. Hit flyttad ur study.py 2026-10-28 (separera när
filen fortsätter att växa); study återexporterar namnen, så `st.utfallsenhet`
och `st._tillforlitlighet` gäller fortfarande.
"""

from __future__ import annotations

import math

from selvra_analysis.stats import COVERAGE_NOTE

KOLUMN_ENHETER = {"steps": "steg", "hr_lowest_bpm": "slag/min", "hrv_avg_ms": "ms",
                  "total_sleep_seconds": "s", "deep_sleep_seconds": "s",
                  "rem_sleep_seconds": "s", "sleep_score": "poäng", "readiness_score": "poäng",
                  "sleep_efficiency_pct": "pp", "stress_avg": "poäng", "stress_max": "poäng"}


def utfallsenhet(spec: dict) -> str:
    kol = str(spec.get("utfall", {}).get("kolumn", ""))
    if kol.endswith("_pct"):
        return "pp"
    return KOLUMN_ENHETER.get(kol, "mmol/L")


def _fmt(x: float) -> str:
    return "obegränsat" if not math.isfinite(x) else f"{x:+.2f}".replace(".", ",")


def _tillforlitlighet(kind: str, beslut: str) -> str:
    """GRADE-betyget på domen: randomiserat startar hög, observation låg;
    ett obestämt beslut är allvarlig imprecision och sänker en nivå."""
    obestamt = beslut.startswith("obestämt")
    if kind == "n1":
        return ("måttlig — randomiserad och förregistrerad, men nedgraderad för imprecision"
                if obestamt else
                "hög — randomiserad och förregistrerad; nivå 1-bevis för personen (OCEBM 2011)")
    return ("mycket låg — icke-randomiserad observation, därtill imprecision"
            if obestamt else
            "låg — icke-randomiserad observation: en dörr till en lottad studie, aldrig ett lås")


def _report(study, record: dict) -> str:  # study: study.Study (otypad: lövmodulen importerar aldrig motorn)
    sp, r, d = study.spec, record["result"], study.design
    unit = "procentenheter" if sp["utfall"].get("matt") == "tid_over_10" or \
        str(sp["utfall"].get("kolumn", "")).endswith("_pct") else utfallsenhet(sp)
    kind = ("randomiserat n-of-1-försök med parade perioder" if study.kind == "n1"
            else "observationsstudie" + (", retrospektiv" if d.get("retrospektiv") else ""))
    lines = [
        f"# {sp['titel']}", "",
        f"*{kind} · studie `{sp['id']}` · låst {record['lock']['locked_at'][:10]} · körd {record['run_at'][:10]}*", "",
        "## Svar", "",
        (f"**{record['beslut'][0].upper() + record['beslut'][1:]}.** Skattning {_fmt(r['estimate'])} {unit} "
         f"({int(r['level'] * 100)} % intervall {_fmt(r['ci_low'])} till {_fmt(r['ci_high'])})."), "",
        f"*Tillförlitlighet (GRADE): {_tillforlitlighet(study.kind, record['beslut'])}.*", "",
        "## Fråga och tes (låsta i förväg)", "",
        f"- **Fråga:** {sp['fraga']}", f"- **Tes:** {sp['tes']}", f"- **Motbevis:** {sp['motbevis']}",
        f"- **Minsta relevanta effekt:** {_fmt(sp['analys']['minsta_relevanta_effekt'])} {unit}", "",
        "## Metod", "",
    ]
    if study.kind == "n1":
        lines += [
            f"- **A:** {d['A']}", f"- **B:** {d['B']}",
            (f"- **Design:** {d['par']} par om två perioder à {d['periodlangd_dagar']} dagar, ordningen inom "
             f"varje par lottad före start; {d.get('tvatt_dagar', 0)} tvättdag(ar) per period räknas inte."),
            (f"- **Utfall:** {sp['utfall']['matt']} glukos {sp['utfall']['fonster'][0]}–{sp['utfall']['fonster'][1]} "
             "lokal tid, medel per period."),
            (f"- **Analys:** parvis randomiseringstest ({'exakt' if r['exact'] else 'Monte Carlo'}), intervall "
             "genom testinvertering. Lottat villkor gäller oavsett följsamhet."), "",
            "## Resultat", "",
            "| | |", "|---|---|",
            f"| Kompletta par | {r['n_pairs']} (bortfall {r['n_pairs_dropped']}) |",
            f"| Skattning A − B | {_fmt(r['estimate'])} {unit} |",
            f"| Intervall | {_fmt(r['ci_low'])} till {_fmt(r['ci_high'])} |",
            f"| p (ingen effekt) | {r['p_value']:.4f} |".replace(".", ","),
            f"| AB-par / BA-par | {_fmt(r['estimate_ab_pairs'])} / {_fmt(r['estimate_ba_pairs'])} |", "",
            "Skiljer sig AB- och BA-paren mycket åt kan en eftereffekt mellan perioderna finnas.",
        ]
    else:
        exp = d["exponering"]
        lines += [
            (f"- **Exponering:** dagar {exp.get('dagar_efter', 0)} dag(ar) efter loggad händelse "
             f"`{exp['handelse']}`, jämfört med övriga dagar, {d['period'][0]} till {d['period'][1]}."),
            (f"- **Utfall:** `{sp['utfall']['kolumn']}` på giltiga dagar." if "kolumn" in sp["utfall"] else
             f"- **Utfall:** {sp['utfall']['matt']} glukos {sp['utfall']['fonster'][0]}–"
             f"{sp['utfall']['fonster'][1]} lokal tid, dagar med minst {sp['utfall'].get('min_tackning_pct', 70)} % "
             "täckning i fönstret."),
            f"- **Analys:** skillnad i medelvärde, cirkulär block-bootstrap, block {r['block_length']} dagar.", "",
            "## Resultat", "",
            f"Exponerade dagar {r['n_exposed']}, jämförelsedagar {r['n_comparison']}.", "",
            "Observationsdata visar samband, inte orsak.", "",
            COVERAGE_NOTE,
        ]
        if d.get("retrospektiv"):
            lines.append("Studien är retrospektiv: datan fanns när den skrevs, så förregistreringen skyddar "
                         "inte mot att frågan valdes efter att mönstret setts.")
    lines += _adherence_lines(d, record.get("foljsamhet"))
    lines += _negative_control_lines(sp, record["negativ_kontroll"])
    lines += _protocol_lines(sp)
    data = record["data"]
    lines += [
        "", "## Spårbarhet", "",
        f"- Studiefil sha256 `{record['lock']['spec_sha256'][:16]}`, pipeline-commit `{record['lock']['pipeline_commit'][:12]}`",
        f"- Dataversion `{data['fingerprint'][:16]}` ({len(data['files'])} källor)",
        f"- Körd vid commit `{record['commit'][:12]}`",
    ]
    return "\n".join(lines) + "\n"


def _outcome_text(o: dict) -> str:
    if "fonster" in o:
        return f"{o['matt']} glukos {o['fonster'][0]}–{o['fonster'][1]} lokal tid"
    return f"`{o['kolumn']}`"


def _adherence_lines(d: dict, adh: dict | None) -> list[str]:
    if adh is None:
        return []
    f = d["foljsamhet"]
    rule = {k: " och ".join(f"{'minst' if op == 'min' else 'högst'} {v:g}" for op, v in f[k].items())
            for k in ("A", "B")}
    lines = ["", "## Följsamhet", "", f"Mätt som `{f['kolumn']}` per dag. Analysen ovan följer lottningen oavsett.", "",
             "| Villkor | Regel | Dagar | Med mätning | Uppfyllda |", "|---|---|---|---|---|"]
    for k in ("A", "B"):
        a = adh[k]
        lines.append(f"| {k} | {rule[k]} | {a['dagar']} | {a['matta']} | {a['uppfyllda']} |")
    return lines


def _negative_control_lines(sp: dict, neg: dict) -> list[str]:
    covers_zero = neg["ci_low"] <= 0 <= neg["ci_high"]
    verdict = ("intervallet täcker noll, som förväntat" if covers_zero else
               "intervallet utesluter noll: något annat än exponeringen skiljer grupperna åt, "
               "och huvudresultatet ska läsas med det i åtanke")
    return [
        "", "## Negativ kontroll", "",
        f"{_outcome_text(sp['negativ_kontroll'])}: {sp['negativ_kontroll']['motivering']}", "",
        (f"Skattning {_fmt(neg['estimate'])} ({int(neg['level'] * 100)} % intervall {_fmt(neg['ci_low'])} "
         f"till {_fmt(neg['ci_high'])}); {verdict}."),
    ]


def _protocol_lines(sp: dict) -> list[str]:
    prot = sp["protokoll"]
    lines = ["", "## Protokoll (CENT 2015)", ""]
    for key, label in (("periodeffekt", "Periodeffekt"), ("overforing", "Överföring"),
                       ("stoppregel", "Stoppregel")):
        if key in prot:
            lines.append(f"- **{label}:** {prot[key]}")
    changes = prot["andringslogg"]
    lines.append("- **Ändringar efter låsning:** " + ("inga" if not changes else "; ".join(map(str, changes))))
    return lines


# --- CLI --------------------------------------------------------------------------------------
