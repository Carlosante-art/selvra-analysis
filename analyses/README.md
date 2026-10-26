# Analyses

One folder per analysis, numbered. Each follows [`ANALYSMALL.md`](../ANALYSMALL.md):

1. `forregistrering.md`: question, data, thesis, falsification criterion, metric definitions and statistical plan. **Committed before any analysis code is written.**
2. `analys.py`: developed on synthetic data only, then frozen by writing its commit hash into the pre-registration.
3. `korningar/`: one record per run on real data (result, commit, data checksums, versions). The first is the confirmatory run.
4. `resultat.md`: data quality decisions, results, conclusions labelled observed / derived / interpreted, limitations, log.

The commit history is the proof that the thesis came first.

| # | Question | Status |
|---|---|---|
| [000](000-exempel-traning/) | Worked example on synthetic data: is time in range higher on training days? | Example, synthetic only |
| [001](001-tre-dagar-hogt/) | What happens in the days after three consecutive high days? | Pre-registration in progress |
