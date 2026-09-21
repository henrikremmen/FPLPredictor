# Driftsette API-et

Dette dokumentet beskriver hvordan `src/api.py` (FastAPI-broen som både
webappen og mobilappen snakker med) kjøres lokalt, på samme Wi-Fi som en
fysisk iPhone, og bak en offentlig HTTPS-adresse. Ingen av trinnene under
krever kodeendringer i mobilappen eller webappen — alt styres av
miljøvariabler.

## Miljøvariabler

| Variabel | Standard | Effekt |
|---|---|---|
| `FPL_API_HOST` | `127.0.0.1` | Sett til `0.0.0.0` for å lytte på alle nettverksgrensesnitt (nødvendig for en fysisk iPhone på samme Wi-Fi). |
| `FPL_API_PORT` | `8000` | Porten uvicorn lytter på. |
| `FPL_API_CORS_ORIGINS` | `localhost:5173/4173` (og 127.0.0.1) | Kommaseparert liste over opprinnelser nettleser-frontenden tillates fra. Native mobilklienter er ikke omfattet av CORS og trenger ikke stå her. |
| `FPL_API_CORS_ORIGIN_REGEX` | (uskrevet) | Valgfritt regex-alternativ til `FPL_API_CORS_ORIGINS`, f.eks. for forhåndsvisnings-URL-er per commit. |
| `DATABASE_URL` | (uskrevet → lokal SQLite) | Sett til en `postgresql://`-URL for at øktregisteret skal ligge i Postgres i stedet for en lokal fil. Krever `pip install psycopg2-binary`. |
| `FPL_SESSIONS_DB_PATH` | `data/local/sessions.db` | Overstyrer SQLite-filstien; brukes også av testene (`:memory:`). |

`.env` i prosjektroten (kopiert fra `.env.example`) dekker fortsatt de
valgfrie eksterne datakildene (odds, football-data.org). Disse nøklene
forlater aldri serveren — se «Hemmeligheter» under.

## Kjøre lokalt for en fysisk iPhone på samme Wi-Fi

```bash
FPL_API_HOST=0.0.0.0 .venv/bin/python run_app.py
```

`run_app.py` skriver ut den lokale IP-adressen og en ferdig `.env`-linje for
`apps/mobile`, f.eks.:

```
Backend lytter på alle nettverk (0.0.0.0:8000).
Fra en iPhone på samme Wi-Fi, sett apps/mobile/.env til EXPO_PUBLIC_API_URL=http://192.168.1.23:8000
```

Telefonen må være på samme Wi-Fi-nettverk som maskinen som kjører backend.
macOS-brannmuren kan be om tillatelse for `python`/`uvicorn` første gang;
godkjenn den innkommende tilkoblingen.

## Sesjoner overlever restart

`STORE` i `src/api.py` holder importerte lag i minnet, men hver økt spores
også i et durabelt register (`src/session_store.py`). Et lag som mangler i
minnet — fordi API-et ble restartet — bygges automatisk på nytt fra
entry-ID, horisont og risikoprofil, og lagrede manuelle korrigeringer under
`data/local/team_overrides/` spilles inn igjen. Klienten merker ingen
forskjell utover en marginalt tregere første forespørsel etter en restart.

Standard lagring er en lokal SQLite-fil. Sett `DATABASE_URL` til en
`postgresql://`-URL for delt, flerinstans-drift; skjema og spørringer i
`session_store.py` er skrevet for å fungere uendret mot begge.

## Delte prognosesnapshots

Alle brukere/økter leser samme frosne prognose fra
`data/raw/live_fpl/capture_*/forecast.csv`. Å oppdatere prognosen
(`POST /api/forecast/refresh` eller `POST /api/team/{id}/refresh`) er derfor
en operasjon som gjelder alle, ikke bare den som trykker knappen.
`RefreshGuard` i `api.py` serialiserer og rate-begrenser disse kallene
(ett om gangen, minimum 30 sekunder mellom kall) slik at flere mobilklienter
som trykker «Oppdater» samtidig ikke gjør den dyre, eksterne innhentingen
flere ganger eller trigger rate-limits hos FPL/odds-API-et.

## Lange jobber og tidsavbrudd

En prognoseoppdatering tar normalt rundt ett minutt. Sett tidsavbruddet i en
eventuell reverse proxy (nginx, Caddy, en PaaS-plattforms edge-proxy) til
minst 120 sekunder for `/api/forecast/refresh` og `/api/team/*/refresh`.
`RefreshGuard` returnerer `409` hvis en oppdatering allerede pågår og `429`
hvis forrige oppdatering var for nylig, slik at klienter kan vise en tydelig
melding i stedet for å henge.

## Docker

```bash
docker build -t fpl-modell-api .
docker run --rm -p 8000:8000 \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/artifacts:/app/artifacts" \
  -v "$(pwd)/models:/app/models" \
  --env-file .env \
  fpl-modell-api
```

`data/`, `artifacts/` og `models/` er ikke bakt inn i imaget — de inneholder
prognoser, sesjonsregisteret og trente modellartefakter som må overleve
redeploys. Monter dem som volumer i produksjon. `Dockerfile` bruker det
fulle `requirements.txt` (inkludert notebook-avhengigheter som ikke trengs i
produksjon); et smalere `requirements-api.txt` er en fremtidig
imagestørrelse-optimalisering, ikke noe dagens oppsett er avhengig av.

## Offentlig HTTPS-backend

API-et er transport-agnostisk: det bryr seg ikke om det nås via HTTP eller
HTTPS, bare om `FPL_API_HOST`/`FPL_API_PORT` og CORS-listen er satt riktig.
TLS termineres normalt av hosting-plattformen (Render, Fly.io, en
reverse proxy foran Docker-containeren, osv.), ikke av uvicorn selv. Når
API-et har en offentlig HTTPS-adresse, pek klientene dit:

- Webfrontend: `frontend/src/api.ts` kaller relative `/api/...`-stier uten
  egen base-URL. I dev proxyer Vite disse til `FPL_API_URL` (se
  `frontend/vite.config.ts`). I produksjon server frontendens bygde filer
  (`frontend/dist`) bak samme domene/reverse proxy som ruter `/api` videre
  til backend-containeren, så koden trenger ikke vite noe om adressen.
- Mobilapp: sett `EXPO_PUBLIC_API_URL=https://din-adresse` i
  `apps/mobile/.env` eller som EAS-miljøvariabel per profil (se
  `apps/mobile/eas.json`).

Ingen kildekodeendring er nødvendig for å bytte fra lokal HTTP til en
offentlig HTTPS-adresse.

## Hemmeligheter

`ODDS_API_KEY`, `ODDS_PLAYER_PROPS` og `FOOTBALL_DATA_API_KEY` leses bare av
serverprosessen fra `.env`/miljøet. De sendes aldri til frontend eller
mobilapp, lagres aldri i prognose-snapshots, og mobilappen har ingen egne
API-nøkler i det hele tatt — den snakker utelukkende med denne backenden.

## Health check

`GET /api/health` returnerer status, oppetid og antall økter i minnet-cachen.
Bruk denne for containerorkestrerings-helsesjekker og oppetidsovervåking.
