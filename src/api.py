"""Local FastAPI bridge between the React UI and the Python FPL engine."""

from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from uuid import uuid4

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from chip_strategy import recommend_chip_strategy
from fpl_app import (
    AppError,
    ImportedTeam,
    import_team,
    optimal_lineup,
    recommend_transfers,
    refresh_forecast,
    sell_candidates,
    transfer_targets,
)


ROOT = Path(__file__).resolve().parents[1]


class TeamImportRequest(BaseModel):
    reference: str = Field(min_length=1)
    horizon: int = Field(default=3, ge=1, le=3)
    risk_profile: str = Field(default="balanced", pattern="^(balanced|stable|upside)$")


class TeamSettingsRequest(BaseModel):
    bank: int = Field(ge=0, le=200)
    free_transfers: int = Field(ge=0, le=5)


class TransferRequest(BaseModel):
    number: int = Field(ge=1, le=5)


class TeamStore:
    def __init__(self) -> None:
        self._teams: dict[str, ImportedTeam] = {}
        self._lock = RLock()

    def add(self, team: ImportedTeam) -> str:
        session_id = uuid4().hex
        with self._lock:
            self._teams[session_id] = team
        return session_id

    def get(self, session_id: str) -> ImportedTeam:
        with self._lock:
            team = self._teams.get(session_id)
        if team is None:
            raise HTTPException(status_code=404, detail="Lagøkten finnes ikke. Last inn laget på nytt.")
        return team


STORE = TeamStore()
app = FastAPI(title="FPL Modell API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:4173", "http://127.0.0.1:4173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type"],
)


def _records(frame: pd.DataFrame) -> list[dict]:
    return json.loads(frame.to_json(orient="records"))


def _json_safe(payload: dict) -> dict:
    """Normalize NumPy scalars left by optimization/DataFrame operations."""
    def convert(value):
        if isinstance(value, np.generic):
            return value.item()
        raise TypeError(f"Unsupported JSON type: {type(value).__name__}")

    return json.loads(json.dumps(payload, default=convert))


def _lineup_payload(team: ImportedTeam) -> dict:
    source = team.lineup_squad if team.lineup_squad is not None else team.squad
    lineup = optimal_lineup(source)
    return {
        "formation": lineup["formation"],
        "projected_total": round(float(lineup["projected_total"]), 4),
        "expected_total": round(float(lineup["expected_total"]), 4),
        "captain_margin": round(float(lineup["captain_margin"]), 4),
        "starters": _records(lineup["starters"]),
        "bench": _records(lineup["bench"]),
    }


def _team_payload(session_id: str, team: ImportedTeam) -> dict:
    return {
        "session_id": session_id,
        "entry_id": team.entry_id,
        "event": team.event,
        "target_event": team.target_event,
        "manager_name": team.manager_name,
        "team_name": team.team_name,
        "bank": team.bank,
        "free_transfers": team.free_transfers,
        "deadline": team.deadline,
        "horizon": team.horizon,
        "risk_profile": team.risk_profile,
        "forecast_path": str(team.forecast_path),
        "chip_status": team.chip_status,
        "squad": _records(team.squad),
        "lineup": _lineup_payload(team),
    }


def _as_http_error(exc: AppError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/team/import")
def load_team(request: TeamImportRequest) -> dict:
    try:
        team = import_team(
            request.reference, ROOT, horizon=request.horizon,
            risk_profile=request.risk_profile,
        )
    except AppError as exc:
        raise _as_http_error(exc) from exc
    session_id = STORE.add(team)
    return _team_payload(session_id, team)


@app.get("/api/team/{session_id}")
def get_team(session_id: str) -> dict:
    team = STORE.get(session_id)
    return _team_payload(session_id, team)


@app.patch("/api/team/{session_id}/settings")
def update_settings(session_id: str, request: TeamSettingsRequest) -> dict:
    team = STORE.get(session_id)
    team.bank = request.bank
    team.free_transfers = request.free_transfers
    return _team_payload(session_id, team)


@app.post("/api/team/{session_id}/transfers")
def transfers(session_id: str, request: TransferRequest) -> dict:
    team = STORE.get(session_id)
    try:
        frame = recommend_transfers(team, number=request.number)
    except AppError as exc:
        raise _as_http_error(exc) from exc
    return {
        "number": request.number,
        "global_optimum": bool(not frame.empty and frame.iloc[0]["is_global_optimum"]),
        "plans": _records(frame),
    }


@app.get("/api/team/{session_id}/market")
def market(
    session_id: str,
    position: str | None = Query(default=None, pattern="^(GK|DEF|MID|FWD)$"),
    max_price: int | None = Query(default=None, ge=30, le=200),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    team = STORE.get(session_id)
    frame = transfer_targets(team, position=position, max_price=max_price, limit=limit)
    return {"players": _records(frame)}


@app.get("/api/team/{session_id}/sells")
def sells(session_id: str, limit: int = Query(default=15, ge=1, le=15)) -> dict:
    team = STORE.get(session_id)
    return {"players": _records(sell_candidates(team, limit=limit))}


@app.post("/api/team/{session_id}/chips")
def chips(session_id: str) -> dict:
    team = STORE.get(session_id)
    try:
        return _json_safe(recommend_chip_strategy(team))
    except AppError as exc:
        raise _as_http_error(exc) from exc


@app.post("/api/forecast/refresh")
def refresh() -> dict:
    try:
        refresh_forecast(ROOT)
    except AppError as exc:
        raise _as_http_error(exc) from exc
    return {"status": "complete"}
