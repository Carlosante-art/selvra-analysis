from pathlib import Path

import duckdb
import pytest

from selvra_analysis.ingest_events import EventLogError, load, read_event_log

TEMPLATE = Path(__file__).parents[1] / "data" / "handelser.mall.csv"


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "handelser.csv"
    path.write_text(text)
    return path


def test_template_is_valid() -> None:
    df = read_event_log(TEMPLATE)
    assert len(df) == 5
    assert set(df["typ"]) <= {"sjukdom", "sensorbyte", "alkohol", "traning", "resa"}


def test_unknown_type_reports_line(tmp_path: Path) -> None:
    path = _write(tmp_path, "start,slut,typ,notering\n2025-01-01,,sjukdom,\n2025-01-02,,fest,\n")
    with pytest.raises(EventLogError, match="rad 3: okänd typ 'fest'"):
        read_event_log(path)


def test_bad_date_reports_line(tmp_path: Path) -> None:
    path = _write(tmp_path, "start,slut,typ,notering\n2025-13-45,,sjukdom,\n")
    with pytest.raises(EventLogError, match="rad 2: kan inte läsa start"):
        read_event_log(path)


def test_missing_log_gives_empty_table(tmp_path: Path) -> None:
    db = tmp_path / "t.duckdb"
    assert load(tmp_path / "does_not_exist.csv", db) == 0
    with duckdb.connect(str(db)) as con:
        cols = [r[0] for r in con.execute("describe raw.personal_events").fetchall()]
    assert cols == ["start", "slut", "typ", "notering", "source_line"]
