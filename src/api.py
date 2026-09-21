"""Local FastAPI bridge between the React UI and the Python FPL engine."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from threading import RLock
from uuid import uuid4

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from chip_strategy import recommend_chip_strategy
from manager_analytics import AnalyticsService
from multiweek_planner import plan_multiweek
from session_store import SessionRegistry
from squad_recommendations import recommend_squads
from strategy_advisor import build_strategy_advice
from fpl_app import (
    AppError,
    ImportedTeam,
    apply_manual_squad_changes,
    clear_team_override,
    import_team,
    load_team_override,
    optimal_lineup,
    recommend_transfers,
    refresh_forecast,
    save_team_override,
    sell_candidates,
    transfer_targets,
)


ROOT = Path(__file__).resolve().parents[1]


class TeamImportRequest(BaseModel):
    reference: str = Field(min_length=1)
    horizon: int = Field(default=3, ge=1, le=8)
    risk_profile: str = Field(default="balanced", pattern="^(balanced|stable|upside)$")


class TeamSettingsRequest(BaseModel):
    bank: int = Field(ge=0, le=200)
    free_transfers: int = Field(ge=0, le=5)


class SquadChangeRequest(BaseModel):
    out_id: int = Field(gt=0)
    in_id: int = Field(gt=0)


class SquadEditRequest(BaseModel):
    mode: str = Field(pattern="^(synchronize|apply_transfers)$")
    changes: list[SquadChangeRequest] = Field(min_length=1, max_length=5)
    bank: int | None = Field(default=None, ge=0, le=200)
    free_transfers: int | None = Field(default=None, ge=0, le=5)


class TransferRequest(BaseModel):
    number: int = Field(ge=1, le=5)
    outgoing_ids: list[int] = Field(default_factory=list, max_length=5)


class PlanRequest(BaseModel):
    weeks: int = Field(default=4, ge=1, le=8)
    discount: float = Field(default=.9, ge=.5, le=1.0)


class TeamStore:
    """In-memory team cache backed by a durable session registry.

    A session survives an API restart: the registry keeps just enough (entry
    ID, horizon, risk profile) to rebuild the ``ImportedTeam`` on demand by
    re-running ``import_team`` and reapplying any saved manual override.
    """

    def __init__(self, registry: SessionRegistry) -> None:
        self._teams: dict[str, ImportedTeam] = {}
        self._registry = registry
        self._lock = RLock()

    def add(self, team: ImportedTeam) -> str:
        session_id = uuid4().hex
        with self._lock:
            self._teams[session_id] = team
        self._registry.put(session_id, team.entry_id, team.horizon, team.risk_profile)
        return session_id

    def get(self, session_id: str) -> ImportedTeam:
        with self._lock:
            team = self._teams.get(session_id)
        if team is not None:
            return team
        pointer = self._registry.get(session_id)
        if pointer is None:
            raise HTTPException(status_code=404, detail="Lagøkten finnes ikke. Last inn laget på nytt.")
        try:
            team = import_team(
                str(pointer.entry_id), ROOT, horizon=pointer.horizon, risk_profile=pointer.risk_profile,
            )
            load_team_override(ROOT, team)
        except AppError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        with self._lock:
            self._teams[session_id] = team
        return team

    def set(self, session_id: str, team: ImportedTeam) -> None:
        with self._lock:
            self._teams[session_id] = team
        self._registry.put(session_id, team.entry_id, team.horizon, team.risk_profile)


def _cors_origins() -> list[str]:
    raw = os.environ.get("FPL_API_CORS_ORIGINS")
    if raw:
        return [origin.strip() for origin in raw.split(",") if origin.strip()]
    return [
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:4173", "http://127.0.0.1:4173",
    ]


STORE = TeamStore(SessionRegistry(ROOT))
ANALYTICS = AnalyticsService()
_STARTED_AT = time.time()
app = FastAPI(title="FPL Modell API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_origin_regex=os.environ.get("FPL_API_CORS_ORIGIN_REGEX"),
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
        "overall_points": team.overall_points,
        "overall_rank": team.overall_rank,
        "team_value": team.team_value,
        "squad_source": team.squad_source,
        "manual_changes": team.manual_changes,
        "forecast_path": str(team.forecast_path),
        "chip_status": team.chip_status,
        "squad": _records(team.squad),
        "lineup": _lineup_payload(team),
    }


def _as_http_error(exc: AppError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - _STARTED_AT, 1),
        "active_sessions": len(STORE._teams),
    }


@app.post("/api/team/import")
def load_team(request: TeamImportRequest) -> dict:
    try:
        team = import_team(
            request.reference, ROOT, horizon=request.horizon,
            risk_profile=request.risk_profile,
        )
        load_team_override(ROOT, team)
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
    team.team_value = int(team.squad["selling_price"].sum() + team.bank)
    team.squad_source = "manual_override"
    save_team_override(ROOT, team)
    return _team_payload(session_id, team)


@app.get("/api/team/{session_id}/squad-options")
def squad_options(session_id: str) -> dict:
    team = STORE.get(session_id)
    columns = [
        "id", "name", "position", "team", "team_id", "price",
        "recommended_points", "opponent", "status", "can_select",
    ]
    available = [column for column in columns if column in team.market]
    options = team.market[available].sort_values(
        ["position", "name", "id"]
    )
    return {"players": _records(options)}


@app.patch("/api/team/{session_id}/squad")
def update_squad(session_id: str, request: SquadEditRequest) -> dict:
    team = STORE.get(session_id)
    try:
        result = apply_manual_squad_changes(
            team,
            [change.model_dump() for change in request.changes],
            request.mode,
            bank=request.bank,
            free_transfers=request.free_transfers,
        )
        save_team_override(ROOT, team)
    except AppError as exc:
        raise _as_http_error(exc) from exc
    payload = _team_payload(session_id, team)
    payload["squad_update"] = result
    return payload


@app.post("/api/team/{session_id}/squad/reset")
def reset_squad(session_id: str) -> dict:
    current = STORE.get(session_id)
    clear_team_override(ROOT, current.entry_id)
    try:
        team = import_team(
            str(current.entry_id), ROOT, horizon=current.horizon,
            risk_profile=current.risk_profile,
        )
    except AppError as exc:
        raise _as_http_error(exc) from exc
    STORE.set(session_id, team)
    return _team_payload(session_id, team)


@app.post("/api/team/{session_id}/transfers")
def transfers(session_id: str, request: TransferRequest) -> dict:
    team = STORE.get(session_id)
    try:
        frame = recommend_transfers(
            team,
            number=request.number,
            forced_outgoing=request.outgoing_ids or None,
        )
    except AppError as exc:
        raise _as_http_error(exc) from exc
    return {
        "number": request.number,
        "outgoing_ids": request.outgoing_ids,
        "global_optimum": bool(not frame.empty and frame.iloc[0]["is_global_optimum"]),
        "plans": _records(frame),
    }


@app.post("/api/team/{session_id}/plan")
def multiweek_plan(session_id: str, request: PlanRequest) -> dict:
    team = STORE.get(session_id)
    try:
        return _json_safe(plan_multiweek(team, weeks=request.weeks, discount=request.discount))
    except AppError as exc:
        raise _as_http_error(exc) from exc


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


@app.post("/api/team/{session_id}/recommended-squads")
def recommended_squads(session_id: str) -> dict:
    team = STORE.get(session_id)
    try:
        return _json_safe(recommend_squads(team))
    except AppError as exc:
        raise _as_http_error(exc) from exc


@app.post("/api/team/{session_id}/strategy")
def strategy(session_id: str) -> dict:
    team = STORE.get(session_id)
    try:
        return _json_safe(build_strategy_advice(team))
    except AppError as exc:
        raise _as_http_error(exc) from exc


@app.get("/api/team/{session_id}/analytics")
def analytics(
    session_id: str,
    event: int | None = Query(default=None, ge=1, le=38),
    league_id: int | None = Query(default=None, gt=0),
) -> dict:
    team = STORE.get(session_id)
    try:
        return _json_safe(ANALYTICS.build(team, event=event, league_id=league_id))
    except AppError as exc:
        raise _as_http_error(exc) from exc


class RefreshGuard:
    """Serializes and rate-limits the expensive, shared forecast refresh.

    The refresh hits the live FPL API (and optional paid sources) and takes
    roughly a minute, and its output is a shared snapshot under
    ``data/raw/live_fpl`` used by every session. Without this guard, several
    mobile clients tapping refresh at once would run the fetch redundantly
    and could trip external rate limits.
    """

    def __init__(self, min_interval_seconds: float = 30.0) -> None:
        self._lock = RLock()
        self._busy = False
        self._last_started: float | None = None
        self._min_interval = min_interval_seconds

    def run(self) -> None:
        with self._lock:
            if self._busy:
                raise HTTPException(status_code=409, detail="En prognoseoppdatering pågår allerede. Prøv igjen om litt.")
            if self._last_started is not None and time.time() - self._last_started < self._min_interval:
                wait = round(self._min_interval - (time.time() - self._last_started))
                raise HTTPException(status_code=429, detail=f"Vent {wait} sekunder før neste oppdatering.")
            self._busy = True
            self._last_started = time.time()
        try:
            refresh_forecast(ROOT)
        finally:
            with self._lock:
                self._busy = False


REFRESH_GUARD = RefreshGuard()


@app.post("/api/forecast/refresh")
def refresh() -> dict:
    try:
        REFRESH_GUARD.run()
    except AppError as exc:
        raise _as_http_error(exc) from exc
    return {"status": "complete"}


@app.post("/api/team/{session_id}/refresh")
def refresh_team(session_id: str) -> dict:
    current = STORE.get(session_id)
    try:
        REFRESH_GUARD.run()
        team = import_team(
            str(current.entry_id), ROOT, horizon=current.horizon,
            risk_profile=current.risk_profile,
        )
        load_team_override(ROOT, team)
    except AppError as exc:
        raise _as_http_error(exc) from exc
    STORE.set(session_id, team)
    return _team_payload(session_id, team)
