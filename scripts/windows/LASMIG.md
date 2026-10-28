# Väckarklockan bor i Windows, inte i WSL

WSL:s cron kör bara när WSL-maskinen är vaken; en laptop som sover missar
07:00 tyst (upptäckt 2026-10-28: syslog-lucka 14:17→22:17, synkvakt 17/21
körde aldrig). Därför ligger schemat i Windows Task Scheduler, som kan väcka
datorn (WakeToRun) och köra ikapp missade starter (StartWhenAvailable):

- **Selvra morgon** (07:00): `scripts/morgon.sh` — loop + båda breven.
  Markörfil gör dubbelstart samma dag till no-op.
- **Selvra synkvakt** (12/17/21): `scripts/synkvakt_korning.sh` — har egen
  en-påminnelse-per-dag-spärr.

Installera om (efter ominstallation/ny dator):
    cp scripts/windows/*.xml /mnt/c/Users/<user>/Downloads/
    schtasks.exe /Create /TN "Selvra morgon" /XML selvra-morgon.xml /F
    schtasks.exe /Create /TN "Selvra synkvakt" /XML selvra-synkvakt.xml /F

Krav: datorn i viloläge (inte avstängd) och "tillåt väckningstimer" på i
Windows energiinställningar. Avstängd dator ⇒ körs vid nästa start i stället.
