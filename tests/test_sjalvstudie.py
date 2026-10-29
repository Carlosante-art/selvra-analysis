"""Självstudien: rör-drift ur rörloggen, grindmönster, ärliga tomlägen."""

from selvra_analysis import sjalvstudie as sj


def test_formandring_flaggas_som_seriebrott() -> None:
    rader = [
        {"tid": "2026-10-29T00:07:27+00:00", "kalla": "garminconnect", "person": "x",
         "bibliotek": "0.3.20", "enhet": "Venu 3", "firmware": "17.05", "falt": ["steps"]},
        {"tid": "2026-11-02T06:00:00+00:00", "kalla": "garminconnect", "person": "x",
         "bibliotek": "0.3.20", "enhet": "Venu 3", "firmware": "17.06", "falt": ["steps"]},
    ]
    fynd = sj.ror_drift(rader)
    assert len(fynd) == 1
    assert "firmware ändrades '17.05' → '17.06'" in fynd[0]
    assert "seriebrotts-kandidat" in fynd[0]


def test_oforandrad_form_ar_tystnad() -> None:
    rad = {"tid": "2026-10-29T00:07:27+00:00", "kalla": "g", "person": "x",
           "bibliotek": "1", "enhet": "V", "firmware": "17", "falt": ["steps"]}
    assert sj.ror_drift([rad, dict(rad, tid="2026-10-30T06:00:00+00:00")]) == []


def test_olika_personer_jamfors_aldrig_med_varandra() -> None:
    a = {"tid": "t1", "kalla": "g", "person": "a", "bibliotek": "1",
         "enhet": "Venu 3", "firmware": "17", "falt": []}
    b = dict(a, person="b", enhet="Venu 2")
    assert sj.ror_drift([a, b]) == []


def test_grindmonster_raknar_dom_och_skal() -> None:
    rader = [{"person": "x", "dom": "STOPP", "skal": "underlag: för få par"}] * 3 \
        + [{"person": "x", "dom": "OK", "skal": ""}]
    ut = sj.grindmonster(rader)
    assert ut[0] == "x: 4 prövningar (OK 1, STOPP 3)"
    assert "vanligaste stoppskäl: underlag" in ut[1]
