# Analysmall

Varje analys går igenom samma nio steg, i samma ordning. **Steg 1–4 skrivs och committas innan du rör datan i kod.** Analyskoden skrivs sedan mot syntetisk data och fryses (steg 4b) innan den körs en gång på riktig data. Git-historiken är beviset för att tesen och metoden kom före resultatet.

- **Full version:** kopiera den här filen till `analyses/NNN-namn/forregistrering.md` och fyll i steg 1–4. Commit. Sedan steg 5–9 i `resultat.md`.
- **Kort version** (daglig träning, cirka 15 min): steg 1, 3, 7 och 8 med en mening var.
- **Tid:** ungefär en tredjedel på steg 1–5. Går nästan all tid till steg 6 har du hoppat över tänkandet.

---

## Förregistrering (committas före analys)

### 1. Frågan och beslutet

- **Fråga** (besvarbar med ja/nej eller en siffra):
- **Beslut** (vem gör vad med svaret?):
- **Om svaret blir A gör jag … / om B gör jag …:**
- **Avgränsning** (period, vad som inte ingår):

> Fälla: "utforska datan" är ingen fråga.

### 2. Kartläggning av datan

| Källa | Vad mäts | En rad är | Period | Kända fel | Nyckel för koppling |
|---|---|---|---|---|---|
| | | | | | |

> Fälla: att räkna medelvärden innan du vet vad en rad är.

### 3. Tes och vad som skulle motbevisa den

- **Tes:**
- **Motbevis** (konkret siffra):
- **Alternativa förklaringar** (minst två):

> Fälla: att bara samla stöd. Försök knäcka din egen tes.

### 4. Analysplan och måttdefinitioner

| Mått | Definition (formel + filter) | Enhet |
|---|---|---|
| | | |

- **Jämförelse** (mot vad?):
- **Metod** (det enklaste som besvarar frågan):
- **Tillräckligt underlag** (minsta antal händelser/dagar):

#### Statistik

- **Primärt utfall** (exakt ett):
- **Effektmått** (vad rapporteras, i vilken enhet? t.ex. "skillnad i medel-TBR, procentenheter, exponerade dagar minus jämförelsedagar"):
- **Minsta effekt som spelar roll** (under detta är svaret "ingen praktisk skillnad" även om intervallet utesluter noll):
- **Osäkerhet:** 95 % intervall med cirkulär block-bootstrap (`selvra_analysis.stats`). Blocklängd: … dagar (förval 7). Seed: …
- **Känslighetsanalyser** (bestäms nu, inte efteråt): blocklängd halva och dubbla; utan artefaktflaggade värden; endast dagar med ≥ 70 % täckning; …
- **Sekundära utfall** (märks *explorativa* i resultatet, ingen slutsats dras från dem ensamma):
- **Saknade data:** dagar under täckningsgränsen räknas som saknade, inte som noll. Dagar som tillhör en annan episod: …
- **Beslutsregel:** tesen håller om … / motbevisas om … / obestämt om intervallet täcker både noll och minsta relevanta effekt.

> Fälla: att ändra definitionen efter att du sett resultatet.
>
> Varför block: dagar från en person hänger ihop. På simulerade data med autokorrelation 0,7 och ingen verklig effekt täcker ett vanligt bootstrap-intervall nollan i bara 65 % av fallen i stället för 95 %; med block om 7 dagar 87 %, med 14 dagar 89 % (`tests/test_stats.py`). Intervallet är alltså fortfarande något för smalt när beroendet är starkt: ett intervall som precis utesluter noll är svagt stöd, inte bevis.

### 4b. Frys analyskoden (blind analys)

1. Committa steg 1–4.
2. Skriv analyskoden i mappen (`analys.py`). Kör den bara mot syntetisk data: `make demo`, sedan `uv run python analyses/NNN-namn/analys.py`. Syntetisk data innehåller inget av svaret, så du kan inte justera koden mot ett resultat.
3. Committa koden. Skriv hashen i förregistreringen som `**Frusen analyskod:** <hash>` och committa.
4. `make build` med din riktiga data, kör analysen **en gång**. Körningen vägrar om koden, pipelinen eller steg 1–4 ändrats efter den frysta committen.
5. Varje körning skrivs till `korningar/` med resultat, commit, dataversion (kontrollsummor, aldrig filnamn) och verktygsversioner. Första körningen på riktig data är den bekräftande. Senare körningar märks som omkörningar.

> Fälla: att "bara fixa en sak" i koden efter att ha sett resultatet. Gör det i så fall öppet: ny frysning, och båda körningarna redovisas.

---

## Genomförande (efter commit av förregistreringen)

### 5. Datakvalitet

Flagga, radera inte. Logga varje beslut: vad, varför, hur många rader. Stäm av radantal mot källan.

### 6. Utforska och analysera

1. Titta: fördelningar, tid, luckor. Grafer före medelvärden.
2. Räkna: exakt enligt steg 4.
3. Robusthet: håller det i delmängder, utan flaggade värden?
4. Nya idéer parkeras längst ner, görs inte nu.

> Fälla: att testa tjugo samband tills ett blir signifikant.

### 7. Slutsats med säkerhetsgrad

| Påstående | Typ (observerat / härlett / tolkat) | Säkerhet (hög / medel / låg) | Grund |
|---|---|---|---|
| | | | |

Höll tesen? Vad kan du **inte** säga utifrån den här datan?

### 8. Kommunicera

1. Svaret, en mening med siffran.
2. Vad det betyder för beslutet.
3. En graf vars rubrik är slutsatsen.
4. Begränsningar.
5. Nästa steg.

### 9. Logg och reflektion

- Länk till körningsposten i `korningar/` (dataversion, commit, frusen commit, versioner). Rensningsbeslut.
- Vad tog längst tid? Vad gör jag annorlunda? Vad lärde jag mig om verkligheten bakom datan?

---

## Parkerade idéer
