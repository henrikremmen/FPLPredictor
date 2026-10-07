# Running and deploying the API

`src/api.py` is the FastAPI backend shared by the web and mobile apps. The same
code runs locally, on a LAN for a physical phone, or behind a public HTTPS URL.
Configuration is controlled by environment variables.

## Environment variables

| Variable | Default | Effect |
|---|---|---|
| `FPL_API_HOST` | `127.0.0.1` | Set to `0.0.0.0` to listen on all interfaces, including LAN connections. |
| `FPL_API_PORT` | `8000` | Port used by uvicorn. |
| `FPL_API_CORS_ORIGINS` | localhost and 127.0.0.1 on ports 5173/4173 | Comma-separated permitted browser origins. Native mobile clients are not subject to browser CORS. |
| `FPL_API_CORS_ORIGIN_REGEX` | Unset | Optional origin regex, for example for preview deployments. |
| `DATABASE_URL` | Unset; local SQLite | A `postgresql://` URL enables shared session storage. Requires `pip install psycopg2-binary`. |
| `FPL_SESSIONS_DB_PATH` | `data/local/sessions.db` | SQLite path override; tests may use `:memory:`. |

The root `.env`, copied from `.env.example`, configures optional odds and
football-data.org sources. Those keys stay on the server.

## Physical iPhone on the same Wi-Fi

```bash
FPL_API_HOST=0.0.0.0 .venv/bin/python run_app.py
```

The launcher prints the local IP and the setting for `apps/mobile/.env`:

```dotenv
EXPO_PUBLIC_API_URL=http://192.168.1.23:8000
```

Use your actual LAN address. Restart Expo after changing the setting. Both
devices must use the same Wi-Fi. Allow incoming Python/uvicorn connections if
the macOS firewall requests permission.

## Sessions and forecasts

`STORE` in `src/api.py` caches imported teams in memory. A durable registry in
`src/session_store.py` records entry ID, horizon and risk profile. After an API
restart, a missing in-memory team is imported again and saved manual corrections
from `data/local/team_overrides/` are reapplied.

SQLite is the default. Use `DATABASE_URL` with PostgreSQL for shared storage
across instances; the registry supports both backends.

All sessions read shared frozen forecasts from
`data/raw/live_fpl/capture_*/forecast.csv`. Refreshing through
`POST /api/forecast/refresh` or `POST /api/team/{id}/refresh` changes the shared
forecast data. `RefreshGuard` serialises refreshes and enforces at least 30
seconds between starts, preventing duplicate expensive requests in one process.

A refresh normally takes around a minute. Set reverse-proxy timeouts to at
least 120 seconds for `/api/forecast/refresh` and `/api/team/*/refresh`.
The guard returns `409` if a refresh is in progress and `429` if the previous
one started too recently.

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

Data, session registries and model artefacts are not baked into the image.
Mount `data/`, `artifacts/` and `models/` as persistent volumes. The Dockerfile
installs only `requirements.txt`; notebook tooling lives in
`requirements-dev.txt`.

## Public HTTPS backend

Terminate TLS at the hosting platform or reverse proxy, and configure the host,
port and CORS settings appropriately.

- **Web:** `frontend/src/api.ts` calls relative `/api/...` paths. During
  development, Vite proxies these to `FPL_API_URL` (see
  `frontend/vite.config.ts`). In production, serve `frontend/dist` behind the
  same origin and route `/api` to the backend.
- **Mobile:** set `EXPO_PUBLIC_API_URL=https://your-backend.example` in
  `apps/mobile/.env` for local development or in the appropriate EAS build
  profile in `apps/mobile/eas.json`.

No client source changes are needed to switch backend addresses.

## Secrets and health checks

`ODDS_API_KEY`, `ODDS_PLAYER_PROPS` and `FOOTBALL_DATA_API_KEY` are read by
server-side capture code. API keys are not sent to the frontend/mobile app or
stored in forecast snapshots. The mobile app communicates only with the backend.

`GET /api/health` returns status, uptime and the number of in-memory sessions
for health checks and monitoring.
