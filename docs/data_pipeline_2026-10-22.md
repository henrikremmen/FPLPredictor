# Egen datainnhenting og skriptet datasett (fase 1)

22. oktober 2026. Gjelder fase 1 i [forbedringsplanen](forbedringsplan_2026-10-22.md):
D1 (automatisk innhenting), D2 (skriptet datasett), D3 (datakontrakt) og
backfill av 2026-27. Beslutning: GitHub Actions i privat repo
`henrikremmen/fpl-data`; FPL-Core-Insights brukes bare til forskning/validering;
spillerprops er ikke aktivert.

## Resultat mot akseptkriteriene

| Kriterium | Status | Bevis |
|---|---|---|
| Workflow har kjørt grønt manuelt | Oppfylt | `workflow_dispatch` (light) 22.10 kl. 15:42 UTC. Botcommit `4253bba` med snapshot der alle fire kall ga HTTP 200. FPL blokkerer ikke Actions-IP-er. |
| Vaastav-kompatible CSV-er for GW1–7 består D3 | Oppfylt | `fpl-data/data/2026-27/gws/gw1–7.csv` og `merged_gw.csv`, 4 551 rader. Kontrakten kjøres før skriving og på nytt fra filene. GW1 er identisk med vaastavs `gw1.csv` i alle 610 rader og alle kolonner unntatt `xP`. |
| `build_dataset.py` gir samme resultat som notebooken | Oppfylt | På notebookens input (vaastav 2016-17 til 2026-27 GW1) er filen byte-identisk med notebookens fil fra 21.09: SHA-256 `be3d0b74…0c56`, 254 441 rader. En enhetstest kjører notebookens egne celler på syntetiske data og sammenligner byte for byte. |

Treningstabellen har nå 2026-27 GW1–7: 258 382 rader, hvorav 4 551 fra
`fpl-data` (F2 løst). Den ligger i `data/processed/`, ikke i tredjeparts-
checkouten, og er ignorert i Git.

## Hva som er laget

- `src/fpl_collect.py`: innhenting for `fpl-data`.
  - `auto` kjøres hver time. Den tar lett snapshot daglig etter 02:30 UTC og i
    T-24t/6t/1t-vinduene, og full rundeeksport når en runde er `finished` og
    `data_checked`.
  - Tilstanden leses fra filene som allerede finnes, så kjøringen er idempotent.
  - `capture_endpoint`/`digest`/`now` (fra `capture_fpl.py`) og
    `checkpoint_for` (fra `deadline_collector.py`) er flyttet hit uendret og
    re-eksporteres der. Modulen bruker bare stdlib, requests, pandas og
    `data_contract.py`.
  - Forespørslene går sekvensielt med 0,5 s mellomrom, retry/backoff og
    User-Agent `fplmodell-snapshot/1.0`.
  - Formatet følger vaastav (MIT, attribusjon i `fpl-data/README.md` og
    `collector/LICENSE-vaastav`). Tillegg: `code`, `history_past.csv`,
    `corrections.csv` og rådata med SHA-256 i manifestet.
  - `xP` er FPLs `ep_next` fra siste snapshot før rundens deadline. Allerede
    skrevne verdier beholdes. GW1–3 mangler snapshot og står tomme. GW4–7 er
    hentet fra lokale `data/raw/live_fpl/capture_*`.
- `src/data_contract.py`: datakontrakten D3.
  - Grensevalidering av `bootstrap-static`, `fixtures`, `element-summary` og
    `event/{gw}/live`.
  - Radsjekker: ingen duplikat `(element, fixture)`, ingen manglende kickoff,
    spillerantall i forventet område, sum av `starts` = 11 per lag og kamp,
    mål = egne mål + motstanders selvmål, minutter 0–120, pris 3,0–20,0 og
    maks 0,1 i endring per døgn, samt rader for begge lag i hver ferdige kamp.
  - `diff_rows` logger FPL-korreksjoner per celle. `map_codes` feiler ved
    tvetydig `code`. Nye spillere midt i sesongen er gyldige.
- `src/build_dataset.py`: erstatter `notebooks/build_expanded_dataset.ipynb`.
  Egne sesonger erstatter vaastavs kopi av samme sesong og må bestå D3 først.
  `src/build_features.py` leser nå fra `data/processed/`.
- `fpl-data`: workflow `.github/workflows/collect.yml` (cron `17 * * * *` og
  `workflow_dispatch`, `contents: write`, ingen secrets), kopier av de to
  modulene, låste versjoner av pandas og requests, og README.
- Tester:
  - `tests/test_fpl_collect.py`: alle D3-regler feiler hver for seg, en ny
    spiller midt i sesongen godtas, og prisgrensen holder.
  - Samme fil: `code`-mapping, korreksjonslogg, planlegging av
    daglig/sjekkpunkt, eksport og `auto` ende til ende med falskt API, at
    ingenting skrives når kontrakten feiler, valg av xP og at kopiene i
    `fpl-data` er like kildene.
  - `tests/test_build_dataset.py`: notebook-ekvivalens og at egen sesong
    erstatter vaastavs og må bestå kontrakten.

## Målt størrelse

| Del | Per enhet | Per sesong (anslag) |
|---|---|---|
| Lett snapshot (fire endepunkter) | ca. 190 kB | ca. 480 snapshots, ca. 92 MB |
| Full eksport, rådata (`element_summaries.tar` 2,4 MB, live, bootstrap, manifest) | ca. 3,0 MB | 38 eksporter, ca. 115 MB |
| CSV-er | `merged_gw.csv` 0,85 MB etter GW7 | Små git-deltaer |

Summen er rundt 200 MB per sesong, altså på planens grense. Alt ligger i git
foreløpig. Blir repoet tungt, kan `element_summaries.tar` flyttes til
Release-assets per runde uten at CSV-formatet endres.

Actions-forbruk: rundt 1 minutt per timekjøring pluss 10–20 minutter per
ukentlig eksport, altså rundt 800 av 2 000 gratis minutter per måned i et
privat repo.

## Verifisering

```
.venv/bin/python -m unittest discover -s tests   -> Ran 169 tests in 2.3s, OK
npm run build --prefix frontend                  -> ✓ built
npm run test:e2e:workspace --prefix frontend     -> 10 passed, 2 skipped (skjermbildetester)
npm run typecheck:mobile                         -> exit 0
npm run test:mobile                              -> 6 suites, 19 tests passed
```

Kjørt etter fase 2, med fase 1-koden på plass.

`auto` er kjørt to ganger lokalt mot ekte API. Første kjøring tok daglig
snapshot. Andre kjøring samme time gjorde ingenting.

## Gjenstår og hvorfor

- **launchd-fallback:** ikke laget. Actions når FPL (første kjøring var grønn).
  Lages hvis FPL senere blokkerer Actions.
- **Moduler som fortsatt leser bare `data-source/data`:** `elo_features.py`,
  `understat_*.py` og `freeze_source_challengers.py` ser fortsatt bare
  vaastavs 2026-27 (kun GW1-resultater). Dette tas i fase 4 (M1) sammen med
  refit.
- **`player_fixture_features.csv`:** ikke bygget på nytt. Det hører til en
  refit-kandidat i fase 4. Produksjonsmodellen er uendret.
- **FPL-Core-Insights:** kryssvalidering av egne CSV-er er ikke kjørt ennå.
  Ifølge beslutningen er kilden kun til forskning.
- **Rådata fra før 22.10 i `fpl-data`:** finnes bare for eksporten, ikke som
  daglige snapshots bakover. Lokale `capture_*` er urørt og brukes som
  xP-kilde.
