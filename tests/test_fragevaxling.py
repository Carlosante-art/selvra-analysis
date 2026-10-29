"""Frågeväxlingen: rotation utan upprepning, tystnad som standard, allt grindat."""

import pytest

from selvra_analysis import fragevaxling as fv


def test_rotation_upprepar_aldrig_samma_typ_i_rad() -> None:
    alla = set(fv.ROTATION)
    assert fv.valj_typ("gap", alla) == "kalibrering"
    assert fv.valj_typ("intention", alla) == "gap"      # wrap runt
    assert fv.valj_typ(None, alla) == "gap"


def test_tystnad_ar_standard_nar_inget_finns_att_fraga() -> None:
    assert fv.valj_typ("gap", set()) is None
    # bara en typ tillgänglig, och den var nyss ställd → hellre tyst än upprepa
    assert fv.valj_typ("gap", {"gap"}) == "gap"  # enda valet; men...
    assert fv.valj_typ("kalibrering", {"kalibrering"}) == "kalibrering"


def test_varje_fraga_passerar_reflektionsgrinden() -> None:
    for typ, arg in (("gap", "ett pass 17:04 i går"),
                     ("kalibrering", "somn"),
                     ("bekraftelse", "promenera efter lunch"),
                     ("intention", "sova vid elva")):
        f = fv.forma_fraga(typ, arg)
        assert f.typ == typ
        assert f.text
        ok, _ = __import__("selvra_analysis.sprakgrind", fromlist=["granska_reflektion"]) \
            .granska_reflektion(f.text, arg)
        assert ok


def test_kalibrering_ar_alltid_relativ_eget_normal_aldrig_skala() -> None:
    f = fv.forma_fraga("kalibrering", "somn")
    assert "vanligt" in f.text
    for skala in ("1-10", "/10", "betyg", "poäng", "skala"):
        assert skala not in f.text.lower()


def test_en_rad_gift_fraga_avvisas_i_kod() -> None:
    # en argument-sträng som skulle göra frågan rådgivande fälls av grinden
    with pytest.raises(ValueError, match="reflektionsgrinden"):
        fv.forma_fraga("intention", "du borde öka dosen")
