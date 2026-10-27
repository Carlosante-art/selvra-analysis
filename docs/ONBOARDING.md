# Kom igång som ny användare

Det här är vägen från noll till en körande analysmotor för en andra person med CGM.
Allt körs lokalt på din egen dator; ingen data lämnar den utan att du ber om det.

## Vad du behöver

| | Krävs | Ger |
|---|---|---|
| Dexcom CGM + Clarity-konto | ja | glukosdata, motorns kärna |
| Garmin-klocka eller Oura-ring | nej | sömn, puls, steg — kontext utan loggning |
| Anthropic API-nyckel | nej | Dreamer: studiedesign och tolkning på klartext |
| Python 3.12+ och [uv](https://docs.astral.sh/uv/) | ja | kör allt |

## Steg 1 — klona och bygg demot

```bash
git clone <repo-url> && cd selvra-analysis
make demo    # syntetisk data, inget personligt: verifierar att allt fungerar
```

## Steg 2 — din egen glukosdata

Exportera CSV från [Dexcom Clarity](https://clarity.dexcom.eu) (valfritt antal filer,
överlapp är ofarligt) och lägg dem i `data/raw/clarity/`. Sedan:

```bash
make build
make rapport    # dina senaste 30 dagar
```

Allt personligt (`data/`, `.env`) är git-ignorerat och stannar på din maskin.

## Steg 3 — valfria kopplingar i `.env`

Skapa `.env` i repo-roten (committas aldrig, skrivs aldrig ut):

```
# Garmin (sömn, puls, steg — hämtas automatiskt i make live)
GARMIN_EMAIL=...
GARMIN_PASSWORD=...

# eller Oura
OURA_TOKEN=...

# Nightscout (din egen instans: glukos + insulin + kolhydrater)
NIGHTSCOUT_URL=https://din-instans.example.com
NIGHTSCOUT_TOKEN=...   # bara om instansen är skyddad

# Dreamer (studiedesign + tolkning via LLM)
ANTHROPIC_API_KEY=...
```

Första Garmin-inloggningen sparar en token i `~/.garminconnect`; lösenordet
behövs bara den gången.

## Steg 4 — den autonoma cykeln

```bash
make dagbok        # morgonrutin: gårdagens siffror + ja/nej-frågor (~30 sekunder)
make skanna        # mönster i din data → studiefrågor
make dreamer fraga="Påverkar träning mitt blodsocker natten efter?"
make loop          # allt ovan i en körning
make schemalagg    # kör loopen automatiskt varje morgon 07:00
```

En studie är ett löfte: du låser fråga, tes och beslutsregel *innan* du ser
effekten, och motorn vägrar köra om något ändrats efteråt. Det är det som gör
svaren värda att lita på. Hela metoden: [`ANALYSMALL.md`](../ANALYSMALL.md)
och [`studies/README.md`](../studies/README.md).

## Live-data var femte minut (valfritt, kräver server)

Med en egen [selvra-diabetes](https://github.com/Carlosante-art/selvra-diabetes)-instans
(Dexcom Share → Supabase) sätter du `ANALYSIS_DB_URL` och `ANALYSIS_USER_ID` i `.env`
och kör `make live` istället för `make build`. Utan server fungerar allt ovan ändå —
du exporterar bara från Clarity lite oftare.
