"""Synkvakten: vaktar alla med nyckel+telefon, tröskel per person, aldrig i smyg."""

from pathlib import Path

from selvra_analysis import synkvakt


def _person(tmp_path: Path, namn: str, *, nyckel: bool, telefon: bool,
            yml: str = "") -> None:
    mapp = tmp_path / "data" / "personer" / namn
    mapp.mkdir(parents=True)
    if nyckel:
        (mapp / "garmin").mkdir()
    if telefon:
        (mapp / "push.json").write_text("{}")
    if yml:
        (mapp / "person.yml").write_text(yml)


def test_vakten_foljer_infran_inte_en_lista(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _person(tmp_path, "a", nyckel=True, telefon=True)
    _person(tmp_path, "b", nyckel=True, telefon=False)   # ingen telefon → ingen notis möjlig
    _person(tmp_path, "c", nyckel=False, telefon=True)   # ingen klocka → inget att vakta
    assert synkvakt.vaktbara() == ["a"]


def test_troskel_lases_per_person_med_arlig_default(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _person(tmp_path, "a", nyckel=True, telefon=True, yml="synk_troskel_timmar: 6\n")
    _person(tmp_path, "b", nyckel=True, telefon=True, yml="namn: X\n")
    assert synkvakt.troskel_for("a") == 6
    assert synkvakt.troskel_for("b") == synkvakt.TROSKEL_TIMMAR
    _person(tmp_path, "d", nyckel=True, telefon=True, yml="synk_troskel_timmar: -3\n")
    assert synkvakt.troskel_for("d") == synkvakt.TROSKEL_TIMMAR  # ogiltigt → default, aldrig 0


def test_kolla_alla_fortsatter_forbi_en_trasig_person(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _person(tmp_path, "a", nyckel=True, telefon=True)
    _person(tmp_path, "b", nyckel=True, telefon=True)
    kollade = []
    monkeypatch.setattr(synkvakt, "kolla", lambda person, skicka=True: (kollade.append(person), 0)[1])
    assert synkvakt.kolla_alla(skicka=False) == 0
    assert kollade == ["a", "b"]
