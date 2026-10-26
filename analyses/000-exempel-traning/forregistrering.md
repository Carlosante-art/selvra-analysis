# 000 · Exempel: skiljer sig tid i målområdet på träningsdagar?

**Status:** exempel på hela arbetsflödet, körs bara på syntetisk data (i CI). Den syntetiska datan har ingen träningseffekt inbyggd, så rätt svar är "ingen skillnad".

### 1. Frågan och beslutet

- **Fråga:** är tid i målområdet (TIR) högre på dagar med loggad träning än på dagar utan?
- **Beslut:** exempel, inget beslut.
- **Avgränsning:** giltiga dagar (≥ 70 % täckning), hela perioden.

### 2. Kartläggning av datan

| Källa | Vad mäts | En rad är | Kända fel | Nyckel |
|---|---|---|---|---|
| `marts.mart_analysis_days` | TIR per dag, träning från händelseloggen | En dag | Ologgad träning räknas som ingen träning | `reading_date` |

### 3. Tes och vad som skulle motbevisa den

- **Tes:** TIR är minst 5 procentenheter högre på träningsdagar.
- **Motbevis:** 95 %-intervallet för skillnaden ligger helt under 5 procentenheter.
- **Alternativa förklaringar:** jag tränar på dagar jag redan mår bra; träning loggas oftare på bra dagar.

### 4. Analysplan och måttdefinitioner

| Mått | Definition | Enhet |
|---|---|---|
| TIR | `tir_pct`, andel mätningar 3,9–10,0 mmol/L | % |
| Träningsdag | `had_training` i händelseloggen | ja/nej |

- **Jämförelse:** träningsdagar mot övriga giltiga dagar.
- **Metod:** skillnad i medelvärde.
- **Tillräckligt underlag:** minst 20 träningsdagar.

#### Statistik

- **Primärt utfall:** `tir_pct` på giltiga dagar.
- **Effektmått:** skillnad i medel-TIR, procentenheter, träningsdagar minus övriga.
- **Minsta effekt som spelar roll:** 5 procentenheter.
- **Osäkerhet:** 95 % intervall, cirkulär block-bootstrap. Blocklängd: 7 dagar. Seed: 1.
- **Känslighetsanalyser:** blocklängd 3 och 14; `tir_pct_clean` (utan artefakter).
- **Sekundära utfall:** inga.
- **Saknade data:** ogiltiga dagar räknas som saknade.
- **Beslutsregel:** tesen håller om hela intervallet ligger över 5; motbevisas om hela ligger under 5; annars obestämt.

### 4b. Frusen analyskod

**Frusen analyskod:** `240492825caf`
