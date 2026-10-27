# Benchmark för designgranskningen

Frågan den besvarar: skiljer granskningen en studie som ser övertygande ut från en som faktiskt kan besvara frågan, och gör den det bättre än en vanlig språkmodell med samma data?

```bash
uv run python -m selvra_analysis.benchmark granska                # designgranskningen (granska.py)
uv run python -m selvra_analysis.benchmark llm                    # en språkmodell, bara studiefil och data
uv run python -m selvra_analysis.benchmark llm --kunskap          # samma modell + docs/studiedesign.md
```

Varje körning skrivs till `resultat/` med manifestets kontrollsumma, så det går att se exakt vilka fall den gällde.

## Uppsättningar

- `fall/`: utvecklingsfallen, skrivna av den som byggde granskningen. De visar att den gör det den är tänkt att göra, men inte att den generaliserar.
- `dold2/`: en andra dold uppsättning, skriven på samma sätt efter att granskningen rättats mot den första. Den mäter om rättningarna generaliserar.
- `dold/`: skrivna av en agent som bara läst forskningsanteckningarna och den här filen, aldrig `granska.py`. Ett fall här som granskningen missar är en verklig svaghet.

**Frysning.** `FRYST.sha256` innehåller kontrollsumman för varje fil. Körningen vägrar om något fall ändrats. Ett fel i ett fall rättas genom att lägga till ett nytt fall, aldrig genom att ändra det gamla efter att resultat setts.

## Måtten

Allt poängsätts maskinellt mot facit; ingen bedömer svaren i efterhand.

| Mått | Betyder |
|---|---|
| stoppfrekvens | andelen fall som ska stoppas och som stoppades |
| av rätt skäl | stoppades med minst ett av facits skäl |
| godkännandefrekvens | andelen giltiga fall som inte stoppades |
| med rätt flaggor | godkändes och bar varje varning facit kräver |
| falska godkännanden | ska stoppas men godkändes: det farliga felet |
| falska stopp | giltiga men stoppades: det som gör systemet oanvändbart |

Ett system som stoppar allt får full stoppfrekvens och noll godkännandefrekvens. Båda måtten redovisas alltid.

**Vad benchmarken inte visar.** Den validerar designgranskningen på just dessa feltyper. Den säger inget om analysmotorns skattningar, om klinisk säkerhet eller om nytta för användare. En bättre poäng än språkmodellen visar en fördel på de här fallen, inte att ingen annan kan göra samma sak.

## Ett fall

En mapp med tre filer.

### `studie.yml`

En studiefil i formatet i [`studies/README.md`](../studies/README.md). Den behöver inte vara giltig: ett fall kan pröva att en trasig fil stoppas.

### `scenario.yml`: den syntetiska personen

```yaml
start: 2025-04-01            # första dagen med data
dagar: 91                    # antal dagar med data
idag: 2025-07-01             # granskningens "idag"; studiens start ska normalt ligga efter
seed: 1
arbete:
  monster: vardagar          # vardagar | rullande | inget
  cykel: [1,1,1,0,0,1,1,0,0,0,1,1,0,0]   # bara rullande: 1 = arbetsdag, upprepas från start
  loggat: true               # är arbetspassen loggade i händelseloggen?
steg:                        # utelämna = ingen wearable alls
  arbete: 11000              # medelsteg en arbetsdag
  ledig: 3500                # medelsteg en ledig dag
  sd: 800
apparat:                     # utelämna = oura hela tiden
  fore: oura
  efter: garmin
  byte: 2025-06-01           # eller: alla: oura
glukos:
  dag: 8.0                   # medel 07–24, mmol/L
  natt: 7.0                  # medel 00–07
  sd: 1.0                    # dag-till-dag-variation
  arbete: 0.0                # tillägg på arbetsdagar
tackning: 1.0                # andel dagar med giltig CGM-data
traning:
  p: 0.3                     # sannolikhet för loggad träning en ledig dag (och arbetsdag om p_arbete saknas)
  p_arbete: 0.3
  natt_effekt: 0.0           # sänkning av natten efter träning, mmol/L
```

Det går att räkna ut framtida lediga dagar ur `cykel` och `start` (dag `start + i` är arbetsdag om `cykel[i % len(cykel)] == 1`).

### `facit.yml`

```yaml
forvantat: STOPP             # STOPP | GODKANN (godkänd, varningar tillåtna)
skal: [positivitet]          # STOPP: minst ett av dessa ska vara stoppskäl
flagga: [apparat]            # GODKANN: varningar som måste finnas med (valfritt)
kategori: kritiskt           # kritiskt | reparerbart | giltigt
motivering: varför, med källa i forskningen
reparation: vad som skulle göra designen giltig (för STOPP)
```

### Skälen

| id | betyder |
|---|---|
| struktur | studiefilen saknar något som behövs för att granska eller genomföra studien |
| tid | tidsplanen håller inte (startdatum, studiens längd) |
| tidsordning | den negativa kontrollen eller utfallet ligger fel i tid i förhållande till exponeringen |
| overforing | en dags villkor kan påverka en annan analyserad dag |
| positivitet | ett villkor går inte att genomföra eller verifiera på de tillåtna dagarna |
| apparat | mätningen av villkoret kommer från olika apparater |
| underlag | för lite giltig data för att testet ska kunna ge ett svar |
| styrka | för låg styrka för att upptäcka den minsta relevanta effekten |
| dagtyp | exponerade dagar och jämförelsedagar skiljer sig i dagstyp |
| data | fel datakälla |
