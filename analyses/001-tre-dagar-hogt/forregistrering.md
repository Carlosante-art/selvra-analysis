# 001 · Tre dagar högt: vad händer dagarna efter?

**Status:** förregistrering pågår. Steg 3–4 fylls i och committas **innan** någon kod körs mot riktig data.

---

### 1. Frågan och beslutet

- **Fråga:** skiljer sig glukosen under dag 1–7 efter en period med minst tre dagar i rad med högt värde från dagar som inte följer på en sådan period?
- **Beslut:** om dagarna efter skiljer sig på ett förutsägbart sätt, till exempel med fler lågvärden, ändrar jag hur jag hanterar perioden efter, och tar upp det med min diabetesvård.
- **Om A** (tydlig skillnad) gör jag: …
- **Om B** (ingen skillnad) gör jag: …
- **Avgränsning:** min egen Dexcom-data, hela exporterade perioden. Endast giltiga dagar (minst 70 % täckning).

### 2. Kartläggning av datan

| Källa | Vad mäts | En rad är | Period | Kända fel | Nyckel |
|---|---|---|---|---|---|
| `marts.mart_analysis_days` | Dagliga CGM-mått + kontext från händelseloggen | En dag | Hela exporten | Täckning, sensorartefakter (flaggkolumner), luckor i loggen | `reading_date` |
| `intermediate.int_cgm_flagged` | Glukos var 5:e min | En mätning | Hela exporten | Tidig sensorperiod, kompressionslågvärden, orimliga hopp, Low/High | `reading_at` |
| `data/raw/handelser.csv` | Sjukdom, sensorbyte, resor, alkohol, träning (självrapporterat) | En händelse | Så långt jag minns | Minnesfel, saknade händelser. Jämför loggade och härledda sensorbyten i `fct_day_context` för att se hur komplett loggen är | Datum |

Verktyg: `consecutive_runs` hittar högperioderna enligt definitionen i steg 4, och `event_windows` ger dag +1 till +7 efter varje period.

### 3. Tes och vad som skulle motbevisa den

*Skriv själv. Det här är steget som gör dig till analytiker.*

- **Tes:**
- **Motbevis** (konkret siffra):
- **Alternativa förklaringar** (minst två):

### 4. Analysplan och måttdefinitioner

*Skriv själv. Tänk särskilt på: vad betyder "högt" exakt? Vad räknas som en ny period om två ligger tätt? Vilka dagar jämför du med?*

| Mått | Definition (formel + filter) | Enhet |
|---|---|---|
| Högdag | | |
| Högperiod | | |
| Utfall | | |

- **Jämförelse:**
- **Metod:**
- **Tillräckligt underlag** (minsta antal högperioder för att dra en slutsats):
