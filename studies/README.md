# Studier

En studie är en fil. Motorn ([`study.py`](../src/selvra_analysis/study.py)) gör resten.

```bash
uv run python -m selvra_analysis.study validera studies/NNN-namn/studie.yml
uv run python -m selvra_analysis.study las      studies/NNN-namn/studie.yml   # sedan: git commit
uv run python -m selvra_analysis.study status   studies/NNN-namn/studie.yml   # hur ofta du vill
uv run python -m selvra_analysis.study kor      studies/NNN-namn/studie.yml   # en gång, när klar
```

1. **validera** kontrollerar filen och säger på svenska vad som saknas.
2. **las** låser: kontrollsumma på filen, pipelinens commit och, för experiment, det lottade schemat. Committa mappen direkt. Commiten är den offentliga tidsstämpeln för att tesen kom före datan.
3. **status** visar framsteg och datakvalitet: avslutade perioder, kompletta par, perioder utan data, vad schemat säger de närmaste dagarna. **Aldrig effekten.** Ett experiment analyseras en gång, när det är klart, så ingen kan avbryta det när det ser bra ut.
4. **kor** gör den enda bekräftande analysen. Den vägrar om filen, schemat eller pipelinen ändrats efter låsningen, om mappen inte är committad, om studien pågår, eller om den redan körts. Resultatet bedöms med den låsta beslutsregeln och skrivs till `slutrapport.md` och `korningar/`.

## Format

```yaml
id: 002-promenad-efter-middag          # samma som mappnamnet
titel: …
fraga: …                               # besvarbar med ett tal
tes: …
motbevis: …                            # konkret

design:
  typ: n1                              # n1 | observation
  # n1: parade perioder, ordningen lottas per par
  A: …                                 # interventionen, exakt (dos, tid)
  B: …                                 # jämförelsen, exakt
  start: 2026-11-02
  par: 12                              # minst 6
  periodlangd_dagar: 2
  tvatt_dagar: 1                       # första dag(ar)na i varje period räknas inte

  # observation:
  # exponering: {handelse: alkohol, dagar_efter: 1}
  # period: [2025-01-01, 2026-10-01]
  # retrospektiv: true                 # datan fanns när studien skrevs

utfall:
  matt: medel                          # medel | topp | tid_over_10 i fönstret
  fonster: ["19:00", "22:00"]          # lokal tid, inom samma dygn
  # observation kan i stället mäta ett helt dygn:
  # kolumn: tbr_pct                    # en kolumn i marts.mart_analysis_days

analys:
  metod: randomiseringstest            # n1 | blockbootstrap (observation, + blocklangd: 7)
  niva: 0.95
  minsta_relevanta_effekt: -1.0        # A minus B, i utfallets enhet; tecknet = förväntad riktning
```

## Exempel: träning och natten efter (observation)

```yaml
design:
  typ: observation
  exponering: {handelse: traning, dagar_efter: 1}   # natten räknas på dagen efter träningen
  period: [2025-11-01, 2026-10-26]
  retrospektiv: true
utfall:
  matt: medel
  fonster: ["00:00", "06:00"]
analys:
  metod: blockbootstrap
  blocklangd: 7
  minsta_relevanta_effekt: -0.5
```

Observation visar samband, inte orsak: du kanske tränar på dagar som redan är annorlunda. Håller sambandet är nästa steg ett n1-experiment med lottade träningsdagar.

**Beslutsregeln är fast:** tesen håller om hela intervallet visar minst den minsta relevanta effekten; motbevisad om hela intervallet ligger under den; annars obestämt. Den bestäms alltså av ett enda tal du skriver innan studien börjar.

Planera antalet par innan du låser: `python -m selvra_analysis.n1 sd` mäter hur mycket utfallet varierar i din data, `python -m selvra_analysis.n1 power` ger styrkan. Se [`N1MALL.md`](../N1MALL.md).
