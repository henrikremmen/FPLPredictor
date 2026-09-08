# Deadline-backtest: datarapport, ikke modellresultater

Åpne `05_deadline_backtest.ipynb` med prosjektets `.venv` og kjør alle celler.
Notebooken er kjørt og inneholder tabeller og figurer. Den leser siste lagrede
kilderevisjon uten nettverkskall. Hent en ny revisjon ved behov:

```sh
.venv/bin/python src/deadline_audit.py
```

## Faktisk resultat

| Sesong | Bootstrap før deadline | Komplett godkjente runder |
|---|---:|---:|
| 2022–23 | 38 | 0 |
| 2023–24 | 38 | 0 |
| 2024–25 | 38 | 0 |
| 2025–26 | 38 | 0 |

Dette utløser planens eksplisitte datarapport-alternativ. Ingen deadline-modell
er trent, og ingen deadline-score er beregnet. Eksisterende kampbaserte
prediksjoner er ikke brukt som erstatning.

Kilderevisjonen undersøkte [FPL-Armband](https://github.com/beeradb/FPL-Armband/blob/main/docs/backfill.md),
[fplcache](https://github.com/Randdalf/fplcache),
[TopMarx/fpl](https://github.com/TopMarx/fpl) og
[vaastav](https://github.com/vaastav/Fantasy-Premier-League).
FPL-Armband sine historiske manifests peker til Wayback-captures av bootstrap;
de dokumenterer ikke historiske fixtures og kampvise historikkversjoner.
fplcache arkiverer også bootstrap. TopMarx sin undersøkte 2025-sesongmanifest
er fra juli 2026; den dokumenterer ikke verdiene ved hver historiske deadline.
Ingen påstand gjøres om at andre tilgjengelige arkiver ikke kan fylle hullene.

Revisjonen pinner FPL-Armband-commit og laster ned 152 bootstrap-payloads med
manifests. Den sjekker dekomprimert payload-SHA-256, archive-/capture-tid,
sesong, deadline og event-tilstand i payloadet, samt spiller-ID, lag og
posisjon. Dette verifiserer samsvar i kildearkivet; alle Wayback-originaler
er ikke hentet på nytt uavhengig. Snapshot-alder vises, og ingen
bootstrap-kontroll alene kan godkjenne en runde.

Rådata og sidecars ligger i `data/raw/deadline_audit/audit_*/evidence`.
Sidecar inneholder URL, HTTP-status, nedlastingstid og SHA-256. Nedlastingstid
er ikke historisk tilgjengelighet. Coverage viser separate flagg og årsaker
per runde. Notebooken lagrer en ny rapport under `artifacts/deadline_backtests`.

## Kode levert og det som gjenstår

- `deadline_features` har rene funksjoner for versjonerte registre, kampoppsett
  og spiller-/laghistorikk. Den gjenskaper grunnvariablene og ensemblets ekstra
  features ved en felles UTC-deadline, med separate blanke rader og separat fasit.
- `deadline_evaluation` har låste form-/HGB-/ensemblemetoder, aggregering,
  rangering, kaptein med ID-tie-break, kandidatsegment og gameweek-bootstrap.
- Begge er grunnlaget for videre kildeintegrasjon, ikke en ferdig sertifisert
  adapter fra bootstrap alene. Produksjonskobling, hele sesongfold-kjøringen
  og modellartefakter er utsatt fordi ingen perioder kvalifiserer.

For å aktivere en ekte backtest kreves verifiserte fixture-snapshots,
versjonert kampvis historikk og komplett fasit, deretter en kildeadapter som
normaliserer dem og knytter hver input til kildebevis. Ikke sett
`audit_approved=True` manuelt for å omgå dette kravet. En gammel fullsesongfil
med kickoff før deadline er ikke i seg selv tilgjengelighetsbevis.

## Verifisering

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_deadline.py' -v
```

Seks tester dekker strenge tidsgrenser/UTC, arkivhash, manglende registry,
nye spillere, blanke/doble runder, endringer etter deadline, flyttede kamper,
klubbskifte, komplett og unik fasit, kapteins-tie-break og like utvalg.
Ingen syntetiske score presenteres som historiske resultater.
