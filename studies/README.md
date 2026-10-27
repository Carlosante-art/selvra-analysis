# Studier

En studie är en fil. Motorn ([`study.py`](../src/selvra_analysis/study.py)) gör resten.

Börja med `/ny-studie` i Claude Code: den intervjuar, hämtar svaren ur din data och skriver filen enligt [`docs/studiedesign.md`](../docs/studiedesign.md).

```bash
uv run python -m selvra_analysis.study validera studies/NNN-namn/studie.yml
uv run python -m selvra_analysis.granska        studies/NNN-namn/studie.yml   # designgranskning på din data
uv run python -m selvra_analysis.study las      studies/NNN-namn/studie.yml   # sedan: git commit
uv run python -m selvra_analysis.study status   studies/NNN-namn/studie.yml   # hur ofta du vill
uv run python -m selvra_analysis.study kor      studies/NNN-namn/studie.yml   # en gång, när klar
```

1. **validera** kontrollerar filen och säger på svenska vad som saknas.
2. **granska** kör de kontroller som kräver data: positivitet per dagstyp, överföring mot verkan, tidsordning för den negativa kontrollen, väntat bortfall, minsta möjliga p och styrka från din egen variation. Resultatet skrivs till `granskning.json`. STOPP blockerar låsning.
3. **las** låser, men bara om granskningen godkänt exakt den versionen av filen: kontrollsumma på filen, pipelinens commit och, för experiment, det lottade schemat. Committa mappen direkt. Commiten är den offentliga tidsstämpeln för att tesen kom före datan.
4. **status** visar framsteg och datakvalitet: avslutade perioder, kompletta par, perioder utan data, vad schemat säger de närmaste dagarna. **Aldrig effekten.** Ett experiment analyseras en gång, när det är klart, så ingen kan avbryta det när det ser bra ut.
5. **kor** gör den enda bekräftande analysen. Den vägrar om filen, schemat eller pipelinen ändrats efter låsningen, om mappen inte är committad, om studien pågår, om underlaget är mindre än det låsta minimumet, eller om den redan körts. Resultatet bedöms med den låsta beslutsregeln och skrivs till `slutrapport.md` och `korningar/`.

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
  # dagar: {veckodagar: [lordag]}      # begränsad lottning: bara dagar där både A och B går
  # dagar_motivering: …
  foljsamhet:                          # krävs av granska: hur varje dags villkor verifieras ur data
    kolumn: steps                      # kolumn i marts.mart_analysis_days, eller manuell
    A: {min: 10000}
    B: {max: 5000}
  verkan:                              # krävs av granska: styr kontrollen av överföring och tidsordning
    typ: traning                       # traning | alkohol | somn | maltid | annat
    borjar: "09:00"                    # tidigast A kan verka
  # genomforbarhet: …                  # om ett villkor aldrig förekommit på de tillåtna dagarna

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

protokoll:                             # CENT 2015; kontrolleras av validera
  periodeffekt: …                      # hur tidstrender hanteras (8a)
  overforing: …                        # n1: hur eftereffekter hanteras (3a, 12c)
  stoppregel: …                        # n1: när försöket avbryts i förtid (7b)
  andringslogg: []                     # ändringar efter låsning; en ändring av filen bryter låset

negativ_kontroll:                      # ett utfall exponeringen inte kan påverka (Lipsitch 2010)
  matt: medel
  fonster: ["07:00", "10:00"]
  motivering: …                        # varför
```

**Den negativa kontrollen** analyseras på exakt samma sätt som huvudutfallet och redovisas i slutrapporten. Visar den en effekt skiljer något annat än exponeringen grupperna åt, och huvudresultatet ska läsas med det i åtanke.

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
  minsta_underlag: {exponerade: 15, jamforelse: 30}   # minst 10 vardera
```

`minsta_underlag` bestäms i förväg. `kor` vägrar före periodens slut och under minsta underlag, och då förbrukas ingenting: studien kan köras när datan finns. `status` visar hur långt det är kvar.

Observation visar samband, inte orsak: du kanske tränar på dagar som redan är annorlunda. Håller sambandet är nästa steg ett n1-experiment med lottade träningsdagar.

**Beslutsregeln är fast:** tesen håller om hela intervallet visar minst den minsta relevanta effekten; motbevisad om hela intervallet ligger under den; annars obestämt. Den bestäms alltså av ett enda tal du skriver innan studien börjar.

Planera antalet par innan du låser: `python -m selvra_analysis.n1 sd` mäter hur mycket utfallet varierar i din data, `python -m selvra_analysis.n1 power` ger styrkan. Se [`N1MALL.md`](../N1MALL.md).
