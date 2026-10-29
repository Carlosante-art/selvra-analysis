"""Friktionsvakten: beteendesignaler, byggaren som mottagare, tystnad utan friktion."""

from datetime import date

from selvra_analysis import friktionsvakt as fv

IDAG = date(2026, 11, 20)


def _grind(person, datum, dom, skal=""):
    return {"person": person, "datum": datum, "forslag": "p02", "dom": dom, "skal": skal}


def test_fastnad_grind_upptacks_efter_troskeln() -> None:
    logg = [_grind("x", f"2026-11-{d:02d}", "STOPP", "för få par; öka design.par")
            for d in range(1, 16)]
    fynd = fv.fastnade_grindar(logg, IDAG)
    assert len(fynd) == 1
    assert "[x]" in fynd[0]
    assert "STOPP" in fynd[0]
    assert "kommer inte vidare" in fynd[0]


def test_kort_streck_ar_tystnad() -> None:
    logg = [_grind("x", f"2026-11-{d:02d}", "STOPP", "x") for d in range(18, 21)]
    assert fv.fastnade_grindar(logg, IDAG) == []
    # ett OK bryter strecket
    logg2 = [_grind("x", f"2026-11-{d:02d}", "OK") for d in range(1, 16)]
    assert fv.fastnade_grindar(logg2, IDAG) == []


def test_framsteg_stall_nar_paren_inte_vaxer() -> None:
    logg = [_grind("x", f"2026-11-{d:02d}", "STOPP", "med väntat bortfall (1 par) kan testet")
            for d in range(1, 16)]
    fynd = fv.framsteg_stall(logg)
    assert fynd
    assert "står stilla på 1" in fynd[0]

    # växande par → ingen stall
    vaxer = [_grind("x", f"2026-11-{d:02d}", "STOPP", f"({d % 4 + 1} par)") for d in range(1, 16)]
    assert fv.framsteg_stall(vaxer) == []


def test_tyst_ror_upptacks() -> None:
    ror = [{"tid": "2026-11-10T07:00:00", "kalla": "garminconnect", "person": "x"}]
    fynd = fv.tysta_ror(ror, IDAG)
    assert fynd
    assert "garminconnect" in fynd[0]
    assert "tunnas ut" in fynd[0]
    # färskt rör → tyst
    assert fv.tysta_ror([{"tid": "2026-11-19T07:00:00", "kalla": "g", "person": "x"}], IDAG) == []


def test_ingen_friktion_sags_kort_och_rapporten_ar_for_byggaren(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(fv, "GRINDLOGG", tmp_path / "g.jsonl")
    monkeypatch.setattr(fv, "RORLOGG", tmp_path / "r.jsonl")
    text = fv.rapport(IDAG)
    assert "för byggaren, aldrig för användaren" in text
    assert "Ingen friktion" in text  # tomma journaler i test = tystnad
