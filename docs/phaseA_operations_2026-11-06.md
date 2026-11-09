# Fase A: drift (O1, O2)

6. november 2026. Gjelder fase A i [planen 06.11](improvement_plan_2026-11-06.md).
Branch `improvement-plan-2026-11` (fra `forbedringsplan-2026-10`). Ingen commits i dette repoet ennå.

Statuslinje ved start (14:33 UTC): GW9 er ferdig og `data_checked`. GW10 har
deadline 6.11 kl. 18:30 UTC og var allerede låst (`loop_gw10_20261106T140930Z`),
så løypa trengte ikke kjøres. GW11: deadline 21.11 kl. 11:00, vinduet åpner
20.11 kl. 05:00 UTC. Siste bot-commit i `fpl-data` var 23.10 kl. 15:07 UTC.
Produksjonsmodellen er uendret (`production_market_0erysib7`).

## Resultat mot akseptkriteriene

| Kriterium | Status | Bevis |
|---|---|---|
| `fpl-data` committer igjen | Oppfylt | Manuell kjøring 42238144550 (6.11 kl. 15:01 UTC) committet `375c184 data: auto` med GW8- og GW9-eksport. Schedule er registrert på nytt (`disable` og `enable`). Fra 6.11 kl. 20:57 kom det grønne schedule-kjøringer omtrent hver 4.–8. time. Det var daglige bot-commits `5dac897` (7.11 kl. 07:17) og `fdfcf80` (8.11 kl. 02:33), kontrollert 8.11. |
| CSV-er for alle `data_checked` runder består D3 | Oppfylt | GW1–9 finnes i `fpl-data/data/2026-27/gws/`. `validate_gameweeks` på `merged_gw.csv` (5 890 rader) består. Eksporten validerer også før skriving. En lokal prøve i en kopi ga 0 korreksjoner. |
| Rødt løp varsler, ikke stille hull | Oppfylt | Kjøringen ble rød i steget «Fail on collection gap» med `Collection gap: 336 h since the previous snapshot`, etter at dataene var committet. GitHub sender e-post om feilede kjøringer. |
| Git-forfatter rettet (F30) | Oppfylt for nye commits | Lokal `user.email` er `159542951+henrikremmen@users.noreply.github.com` i både FPLmodell og `fpl-data`. `988a9fc` har den nye adressen. Global config er fortsatt `youremail@example.com`. Historikken er ikke skrevet om. |
| Banner og låseknapp testet | Oppfylt | Testene dekker lukket, åpent og låst vindu og en tapt GW9 (`tests/test_prospective_loop.py`). API-et kjører i bakgrunnen, hindrer overlapp og avviser låst runde eller lukket vindu (`tests/test_api.py`). Bannerteksten er testet i `apps/mobile/__tests__/loop-banner.test.ts`, og banner og knapp i e2e-testen `lock banner …`. Løypa avviser fortsatt dobbel låsing selv. |
| README og handbook oppdatert | Oppfylt | `README.md`, `docs/handbook.md` (avsnitt om fpl-data og om løypa) og `docs/REPO_GUIDE.local.md`. |

## O1: årsak

- Workflowen `collect` er `active`, og alle seks kjøringer (22.–23.10) var
  grønne. Loggen inneholder ingen feil.
- GitHub opprettet ingen schedule-kjøring etter 23.10 kl. 15:06 UTC, heller
  ingen feilede. Allerede første døgn ble bare 5 av 24 timesslag kjørt.
  Hendelser for repoet og innstillingene for Actions (`enabled`,
  `allowed_actions: all`) viser ingenting galt.
- Koden er ikke årsaken. Samme collector kjørt lokalt mot en kopi eksporterte
  GW8–9 uten kontraktbrudd.
- Konklusjon: schedule-hendelsene sluttet å komme fra GitHub. GitHub
  dokumenterer at planlagte kjøringer kan forsinkes eller droppes. Hvorfor de
  stoppet helt, kan ikke ses i loggen. Faktureringsdata krever `user`-scope
  (`gh auth refresh -h github.com -s user`) og er ikke sjekket. Kjøringene hadde
  0 fakturerbare minutter.
- Tiltak: schedule er registrert på nytt (`gh workflow disable/enable`), og det
  er gjort en manuell backfill. Ingen ny workflow, ingen secrets.

## Hva som er laget

- `src/fpl_collect.py`: `auto` returnerer `gap_hours`, timer siden forrige
  snapshot, og `gap_alert` når verdien er over 36. Kopien i
  `fpl-data/collector/` er lik (testen sjekker det).
- `fpl-data/.github/workflows/collect.yml` (commit `988a9fc`, pushet etter ditt
  ja): resultatet lagres i `$RUNNER_TEMP`, og etter commit kommer steget
  «Fail on collection gap».
- `src/data_quality.py`: `fpl_data_freshness` gir alder på siste snapshot i den
  lokale klonen, `stale` over 36 timer og eksporterte runder.
- `src/prospective_loop.py`: `status()` gir neste deadline ut fra
  deadline-tider, ikke `is_next`, slik at også en gammel capture virker. Den gir
  også vindusstart, om vinduet er åpent, om runden er låst, hvilken pakke som
  låste den, og `missed_locks` (runder fra GW8 uten pakke).
- `src/api.py`: `GET /api/loop/status` og `POST /api/loop/lock`. `LoopJob`
  kjører `prospective_loop.auto` i en bakgrunnstråd med tilstanden
  idle/running/complete/failed. Den startes bare manuelt og har ingen
  tidsplan.
- Felles bannertekst i `packages/shared/src/loop.ts` (`loopBanner`).
  - Web: `LockBanner` i `frontend/src/Workspace.tsx`, montert over
    prognosestatusen på alle sider.
  - Mobil: `apps/mobile/src/components/LockBanner.tsx` på Overview.
  - Banneret vises bare når noe trengs: åpent vindu, en kjørende eller feilet
    lås, tapte runder eller gammel fpl-data.
- Typer og klient: `LoopStatus`, `loopStatus()` og `lockRound()` i
  `packages/api-client`.

## Verifisering

Hele settet ble kjørt etter fase B og dekker også A (se
[fase B](phaseB_numbers_2026-11-06.md)): 199 Python-tester, web-build, 14 e2e
(2 hoppes over uten `SCREENSHOT_DIR`), mobil-typecheck og 59 mobiltester, alle
grønne. Under fase A ble enhetstestene, e2e og mobiltestene kjørt hver for seg
etter endringene.

## Gjenstår

- GitHub kjører fortsatt bare noen av timesslagene (8 kjøringer på 36 timer).
  Det holder for daglig snapshot og eksport. T-24t/6t/1t-sjekkpunktene kan
  likevel bli truffet sjeldent.
- Den globale git-adressen (`git config --global user.email`) er ikke endret.
