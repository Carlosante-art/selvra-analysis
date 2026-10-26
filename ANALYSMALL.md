# Analysmall

Varje analys går igenom samma nio steg, i samma ordning. **Steg 1–4 skrivs och committas innan du rör datan i kod.** Git-historiken är beviset för att tesen kom före resultatet.

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

> Fälla: att ändra definitionen efter att du sett resultatet.

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

- Datum, dataversion, period, commit, rensningsbeslut.
- Vad tog längst tid? Vad gör jag annorlunda? Vad lärde jag mig om verkligheten bakom datan?

---

## Parkerade idéer
