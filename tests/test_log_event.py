from pathlib import Path

from selvra_analysis.ingest_events import read_event_log
from selvra_analysis.log_event import append_event


def test_notes_with_commas_stay_one_event(tmp_path: Path) -> None:
    log = tmp_path / "handelser.csv"
    append_event(log, "2026-10-24", "traning", notering='löpning, 5 km "lugnt"')
    log.write_text(log.read_text().rstrip("\n"))  # hand-edited file without final newline
    append_event(log, "2026-10-22", "sjukdom", slut="2026-10-23")
    df = read_event_log(log)
    assert len(df) == 2
    assert df.iloc[0]["notering"] == 'löpning, 5 km "lugnt"'
    assert df.iloc[1]["slut"] == "2026-10-23"
