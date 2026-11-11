# Fase G: scenarioer (P5, U19, T4)

8. november 2026. Gjelder fase G i [planen 06.11](improvement_plan_2026-11-06.md).

## Resultat mot akseptkriteriene

| Kriterium | Status | Bevis |
|---|---|---|
| Plan A/B | Oppfylt | `scenarios.compare_plans`: Hold, Plan A (beste) og Plan B (beste uten A sine kjøp første uke). Samme horisont og inndata, med netto xP, hits, bank og FT. Ekte lag (3 GW): Hold 150,1, A 154,5 (+4,4) og B 154,4 (+4,3) på 4,7 s. Testet i `tests/test_scenarios.py`. |
| Overstyring med reset | Oppfylt | «Your assumptions»: din sjanse for at spilleren spiller erstatter FPLs i alle beregninger (`overrides` i alle optimeringskall, `apply_overrides`). Antakelsene er en del av cache-nøkkelen og lagres bare i nettleseren. Banner på alle sider med «Reset». Aldri lagret på serveren og aldri brukt i trening. Testet i e2e (`scenarios: …`) og `ScenarioTests`. |
| Bruddpunkt | Oppfylt | `scenarios.breakpoint`: bisection på sjansen for at én spiller spiller, til handlingen i første uke skifter. Svaret er tekst, for eksempel «… if Upgrade's chance of playing falls below 44 %». Når handlingen ikke avhenger av spilleren, sier den det (ekte lag: Schade). |
| Robusthet med lagret seed | Oppfylt | `scenarios.robustness`: hver kandidat beholder sin egen handling i første uke og sin videre plan. Alle scores på de samme 50 trekkene (Q10–Q90-fordeling per spiller og GW) med seed 20261108, som returneres og vises. Resultatet formuleres som «Chosen in X % of scenarios», ikke som sannsynlighet for å vinne. Samme seed gir samme svar (testet). Ekte lag: Hold 16 %, A 48 %, B 36 %. |
| Journal fryses før deadline | Oppfylt | `decision_journal.record` avviser oppføringer etter deadline og ukjente valg. Filene `journal_gw<N>_<tid>.json` skrives aldri over, og den siste før deadline teller. Utfallet regnes etter fpl-data-eksport. Testet i `tests/test_decision_journal.py` og e2e. |
| T4 felles regelversjon | Oppfylt | `src/fpl_rules.py` brukes av flerukeplanen, chip-modulen, backtesten, appen og skyggesesongen: troppform, XI-grenser, maks per klubb, hit, salgspris, FT, chip-halvdeler og `RULES_VERSION`. `tests/test_fpl_rules.py` tester grensene og at alle motorene bruker de samme objektene. Kopien av `RULES_VERSION` i den frittstående collectoren må være lik. |

## Hva som er laget

- **P5** `src/scenarios.py` og API-et:
  - `POST /api/team/{id}/scenarios` (A/B/hold og robusthet, cachet);
  - `POST /api/team/{id}/scenarios/breakpoint`;
  - `overrides` i `ConstraintsRequest`.
- **U19** `src/decision_journal.py` og API-et:
  - `POST`/`GET /api/team/{id}/journal`.
  - Lagres i samme mappe som skyggesesongen (`artifacts/shadow_season/<sesong>_<lag>/`).
  - Hver oppføring fryser rådet, alternativene (hold, A og B), valget ditt,
    notat, prognosetid, tid for spillerdata og XI-ene som scores etterpå.
- **T4** `src/fpl_rules.py`. `fpl_app.selling_price` og `chip_inventory` bruker
  regelmodulen; dupliserte konstanter er fjernet.
- Web:
  - Transfers & plan → **Scenarios**: tabell, robusthet, antakelser og
    bruddpunkt.
  - History → **Decision journal**.
  - Overview-kortet: «Record my decision» og «Plan A / B and scenarios».
  - Antakelsesbanner på alle sider.
- Mobil: «Plan A / B, scenarios and journal» (`/scenarios`) fra Overview, med
  sammenligning, robusthet, registrering og journal. Antakelser og bruddpunkt
  redigeres bare på web, men lagrede antakelser følger med kallene på samme
  enhet.
- Skjermbilder: `artifacts/ui_screenshots/20261108_phaseG_after/` (web, inkl.
  `17-scenarios` og `18-journal`) og `mobile/scenarios.png` (ekte data).

## Verifisering

```
.venv/bin/python -m unittest discover -s tests   # 235 OK
npm run build --prefix frontend                  # OK
npm run test:e2e:workspace --prefix frontend     # 18 passert, 2 skjermbildetester hoppet over
npm run typecheck:mobile                         # OK
npm run test:mobile                              # 62 OK
```

## Gjenstår

- Antakelser og bruddpunkt redigeres ikke på mobil.
- Robustheten bruker uavhengige spillertrekk (M15 med felles kamputfall er
  senere). Snittpoengene i scenarioene ligger over forventningen fordi
  fordelingshalen over Q90 er en antakelse. Andelen er det som rapporteres.
- Journalens utfall regnes uten autosubs, likt for råd og hold.
