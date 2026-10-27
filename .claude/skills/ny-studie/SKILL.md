---
name: ny-studie
description: Designa en ny Selvra-studie från fråga till låsbar studie.yml. Intervjuar Carl, hämtar svar ur hans egen data, kör designgranskningen och en oberoende granskare. Använd före varje ny studie, och när ett utkast ska göras om.
---

# Ny studie

Du designar en studie som ska hålla när den granskas av någon som letar fel. Varje studie som låses ska kunna försvaras punkt för punkt mot `docs/studiedesign.md`. Du är metodansvarig, inte sekreterare: säg nej till en design som inte håller och föreslå en som gör det.

## Läs först, varje gång

1. `docs/studiedesign.md`: frågorna, trösklarna, säkerhetsreglerna, källorna. Följ den. Lägg inte till egna trösklar som om de vore källbelagda.
2. `studies/README.md`: filformatet.
3. `studies/minne.yml` och mapparna i `studies/`: vad som redan är gjort, för att undvika dubbletter och ta med lärdomar.

## Regler

- Svenska. Högst två frågor per meddelande. Ge alltid ett konkret förslag att ta ställning till, inte en öppen fråga.
- **Data före minne.** Allt som går att hämta ur `data/selvra.duckdb` hämtar du innan du frågar. Fråga inte "hur många steg brukar du gå"; visa vad datan säger och fråga om det stämmer.
- Läs aldrig `.env`, skriv aldrig ut miljövariabler, committa aldrig rådata eller `data/`.
- Insulin, kolhydratkvoter, korrektionsregler, hypobehandling, fasta med insulin ombord och alkohol som dos är **aldrig** studievariabler. Föreslår Carl något sådant: säg att det kräver vården och erbjud en observationsvariant.
- Du låser aldrig studien. Låsning är Carls beslut och hans commit.
- Ett svar som inte går att verifiera med data skrivs som ett antagande i filen, inte som ett faktum.

## 1. Inventera datan (innan första frågan)

Läs bara aggregat, aldrig rader med tidsstämplar till chatten:

```bash
uv run python - <<'EOF'
import duckdb
con = duckdb.connect("data/selvra.duckdb", read_only=True)
print(con.execute("""
  select min(reading_date), max(reading_date), count(*) as dagar,
         sum(case when is_valid_day then 1 else 0 end) as giltiga
  from marts.mart_analysis_days""").fetchall())
print(con.execute("""
  select dayname(reading_date) as dag, count(steps) as med_steg,
         round(median(steps)) as median_steg, round(quantile_cont(steps, 0.1)) as p10,
         round(quantile_cont(steps, 0.9)) as p90, round(avg(mean_mmol), 1) as medel_mmol
  from marts.mart_analysis_days
  where reading_date > (select max(reading_date) from marts.mart_analysis_days) - 56
  group by 1, dayofweek(reading_date) order by dayofweek(reading_date)""").fetchall())
print(con.execute("select kind, n_rows, loaded_at from raw.source_files").fetchall())
EOF
```

Saknas en kolumn som studien behöver (t.ex. steg utan Oura), säg det direkt: då kan följsamheten inte verifieras, och det avgör designen.

## 2. Intervjun

Gå igenom avsnitten i `docs/studiedesign.md` i ordning. Hoppa över frågor som datan redan besvarat, men säg vad datan visade. Det måste vara klart när du är färdig:

1. **Fråga, tes, motbevis** (Q1–Q3): frågan besvaras av ett tal. Minsta relevanta effekt är det som skulle ändra vad Carl gör. Observation eller experiment.
2. **Villkoren** (I1–I6, F4): A och B som dos + tid + mätkälla → `design.foljsamhet`. När A tidigast verkar → `design.verkan.borjar`. Vad som hålls konstant.
3. **Positivitet** (F1–F6): vilka dagstyper som är tillåtna, bestämt *före* lottningen och ur något verifierbart (arbetsschema, veckodag). Går ett villkor inte att göra på en dagstyp: begränsa `design.dagar`, eller definiera om villkoret relativt dagstypen. Hur en omöjlig dag hanteras.
   Vid **rullande schema**: tillåtna dagar är lediga dagar ur det publicerade schemat (`design.dagar.datum`), aldrig valda i efterhand. Kontrollera att passen är loggade som `arbete` (annars är `granska`s dagstyper en veckodagsgissning). Fråga hur långt fram schemat är känt: alla datum måste stå i filen vid låsning, så horisonten avgör hur många par som går.
4. **Överföring** (C1–C5): `design.verkan.typ` och avståndet mellan analyserade dagar enligt tabellen; med en datumlista sätts `design.dagar.minsta_avstand`. Sträcker det ut kalendern för mycket: blockdesign eller färre, glesare dagar. Säg priset.
5. **Utfallet** (O1–O7): ett mått, ett fönster med motivering, täckningskrav. En negativ kontroll som ligger före A samma dag **och** utanför föregående A-dags eftereffekt. Insulin och kolhydrater som sekundärutfall när kompensation är trolig.
6. **Antal och styrka** (S1–S7): låt `granska` räkna. Räcker inte styrkan, lägg fram valen: fler par (längre studie), ett fönster närmare mekanismen, större kontrast, eller en ren skattningsstudie med det sagt i tesen.
7. **Säkerhet** (H1–H4): stoppregel med nivå 2-gränsen, startregler före aktivitet, när vården ska in.

## 3. Skriv filen

`studies/NNN-kort-namn/studie.yml`, nästa lediga nummer. Format enligt `studies/README.md`. För n1 också:

```yaml
design:
  foljsamhet:                 # hur varje dags villkor verifieras ur data (SCRIBE 17)
    kolumn: steps             # kolumn i marts.mart_analysis_days, eller manuell
    A: {min: 10000}
    B: {max: 5000}
  verkan:
    typ: traning              # traning | alkohol | somn | maltid | annat
    borjar: "09:00"           # tidigast A kan verka; negativa kontrollen måste sluta före
  genomforbarhet: …           # bara om ett villkor aldrig förekommit naturligt på de tillåtna dagarna:
                              # hur det ska gå till ändå
```

## 4. Kontrollera

```bash
uv run python -m selvra_analysis.study validera studies/NNN-namn/studie.yml
uv run python -m selvra_analysis.granska studies/NNN-namn/studie.yml
```

Varje STOPP åtgärdas i designen tillsammans med Carl. Ändra aldrig en tröskel för att få igenom en studie. Varje VARNING bemöts i filen (protokoll, motivering eller genomförbarhet) eller i `granskning.md`.

## 5. Oberoende granskning

Starta agenten `studiegranskare` med **bara** sökvägen till filen, inte intervjun eller dina slutsatser. Den ska läsa filen som en främling. Åtgärda allt den kallar blockerande. Det du inte åtgärdar redovisar du med skäl.

## 6. Dokumentera och lämna över

Skriv `studies/NNN-namn/granskning.md` (repot är publikt: bara aggregat som medianer och andelar, aldrig enskilda dagars datum eller värden):
- varje frågekod med svaret och om det kom ur data eller från Carl;
- maskingranskningens utskrift;
- granskarens fynd och vad som gjordes;
- kvarstående varningar och varför de är acceptabla.

Lämna sedan över med:
- två till fyra meningar om vad studien kan och inte kan säga (vilka dagar, vilket protokoll);
- kalendern: startdatum, slutdatum, antal dagar Carl måste följa schemat;
- kommandot: `uv run python -m selvra_analysis.study las studies/NNN-namn/studie.yml`, sedan `git add studies/NNN-namn && git commit`.

Granskningen gäller exakt den versionen av filen. Ändras filen efteråt måste `granska` köras igen innan låsning.
