FROM python:3.13-slim AS api

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

# data/, artifacts/ and models/ hold forecasts, session state and trained
# artifacts. They are not baked into the image: mount a persistent volume
# over them (see docs/deploy.md) so refreshed forecasts and sessions survive
# container restarts and redeploys.
RUN mkdir -p data artifacts models

ENV FPL_API_HOST=0.0.0.0 \
    FPL_API_PORT=8000 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

CMD ["uvicorn", "api:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
