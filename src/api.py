"""Local FastAPI bridge between the React UI and the Python FPL engine."""

from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hmac
import json
import os
import time
from pathlib import Path
from threading import RLock, Thread
from uuid import uuid4

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from dotenv import dotenv_values
from pydantic import BaseModel, Field

import chat
import prospective_loop
from autosub_value import lineup_value
from chip_strategy import recommend_chip_strategy
import data_quality
from data_quality import fpl_data_freshness
from manager_analytics import AnalyticsService
from multiweek_planner import plan_multiweek, plan_with_context
from result_cache import ResultCache, cache_key
from scenarios import apply_overrides, breakpoint, compare_plans, robustness
import decision_journal
from session_store import SessionRegistry
from squad_recommendations import recommend_squads
from strategy_advisor import build_strategy_advice, lineup_after
import copy_check
import top_managers
from fpl_app import (
    AppError,
    ImportedTeam,
    apply_manual_squad_changes,
    clear_team_override,
    import_team,
    load_team_override,
    optimal_lineup,
    override_mtime,
    recommend_transfers,
    refresh_forecast,
    save_team_override,
    sell_candidates,
    transfer_targets,
)


from decision_workspace import constrained_team, context, fixture_ticker, player_detail, changes_since_previous, compare_players, change_horizon

ROOT = Path(__file__).resolve().parents[1]
# One shared secret for every route but the health check, from the environment or the root .env.
API_TOKEN = (os.environ["FPL_API_TOKEN"] if "FPL_API_TOKEN" in os.environ
             else dotenv_values(ROOT / ".env").get("FPL_API_TOKEN") or "").strip()


def _require_token_when_exposed(host: str | None, token: str) -> None:
    if host == "0.0.0.0" and not token:
        raise RuntimeError("FPL_API_HOST=0.0.0.0 opens the API to the whole network. "
                           "Set FPL_API_TOKEN in .env first (see docs/deploy.md).")


_require_token_when_exposed(os.environ.get("FPL_API_HOST"), API_TOKEN)


class TeamImportRequest(BaseModel):
    reference: str = Field(min_length=1)
    horizon: int = Field(default=3, ge=1, le=8)
    risk_profile: str = Field(default="balanced", pattern="^(balanced|stable|upside)$")


class TeamSettingsRequest(BaseModel):
    bank: int = Field(ge=0, le=200)
    free_transfers: int = Field(ge=0, le=5)


class HorizonRequest(BaseModel):
    horizon: int = Field(ge=1, le=8)


class SquadChangeRequest(BaseModel):
    out_id: int = Field(gt=0)
    in_id: int = Field(gt=0)


class SquadEditRequest(BaseModel):
    mode: str = Field(pattern="^(synchronize|apply_transfers)$")
    changes: list[SquadChangeRequest] = Field(min_length=1, max_length=5)
    bank: int | None = Field(default=None, ge=0, le=200)
    free_transfers: int | None = Field(default=None, ge=0, le=5)


class ConstraintsRequest(BaseModel):
    locked_ids: list[int] = Field(default_factory=list, max_length=15)
    excluded_ids: list[int] = Field(default_factory=list, max_length=800)
    # P1: reserve GK, bench 1, 2, 3. Omitted = the defaults in fpl_app.BENCH_WEIGHTS.
    bench_weights: list[float] | None = Field(default=None, min_length=4, max_length=4)
    # P5 "Your assumptions": chance of playing (0–1) per player; request-only, never stored or trained on.
    overrides: list[dict] = Field(default_factory=list, max_length=15)
    # L3 autopilot policy for the strategy; omitted = today's defaults (2.0 per transfer, any hit).
    roll_margin: float | None = Field(default=None, ge=0, le=10)
    max_hit: int | None = Field(default=None, ge=0, le=20)


class CompareRequest(ConstraintsRequest):
    out_id: int = Field(gt=0)
    in_id: int = Field(gt=0)


def _constrained(team, request):
    weights = request.bench_weights
    if weights is not None and any(not 0 <= w <= 1 for w in weights):
        raise HTTPException(status_code=422, detail="Bench weights must be between 0 and 1.")
    try:
        team = constrained_team(team, request.locked_ids, request.excluded_ids)
    except AppError as exc:
        raise _as_http_error(exc) from exc
    team = replace(team, bench_weights=tuple(weights)) if weights is not None else team
    if request.roll_margin is not None or request.max_hit is not None:
        team = replace(team, roll_margin=team.roll_margin if request.roll_margin is None else request.roll_margin,
                       max_hit=request.max_hit)
    try:
        return apply_overrides(team, request.overrides)
    except (AppError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc) or "Invalid assumption.") from exc


class TransferRequest(ConstraintsRequest):
    number: int = Field(ge=1, le=5)
    outgoing_ids: list[int] = Field(default_factory=list, max_length=5)


class PlanRequirement(BaseModel):
    """P4: own_by / sell_in need player_id and event; max_club needs team_id; max_position needs position."""
    kind: str = Field(pattern="^(own_by|sell_in|max_club|max_position)$")
    player_id: int | None = Field(default=None, gt=0)
    event: int | None = Field(default=None, ge=1, le=38)
    team_id: int | None = Field(default=None, gt=0)
    position: str | None = Field(default=None, pattern="^(GK|DEF|MID|FWD)$")
    limit: int | None = Field(default=None, ge=0, le=5)


class PlanRequest(ConstraintsRequest):
    weeks: int = Field(default=4, ge=1, le=8)
    discount: float = Field(default=.9, ge=.5, le=1.0)
    chips: bool = False  # P2: plan Bench Boost, Triple Captain, Free Hit and Wildcard too
    requirements: list[PlanRequirement] = Field(default_factory=list, max_length=6)


MAX_TEAMS = 32


class TeamStore:
    """In-memory team cache backed by a durable session registry.

    A session survives an API restart: the registry keeps just enough (entry
    ID, horizon, risk profile) to rebuild the ``ImportedTeam`` on demand by
    re-running ``import_team`` and reapplying any saved manual override. The
    same rebuild serves a team evicted when more than MAX_TEAMS are cached.

    Saved corrections belong to the FPL entry, not the session: when another
    session (the phone vs the web app) saved or cleared one since this team
    was built, ``get`` picks it up before anything reads or overwrites it.
    Stored teams are never changed in place; routes ``set`` a new copy.
    """

    def __init__(self, registry: SessionRegistry, max_teams: int = MAX_TEAMS) -> None:
        self._teams: OrderedDict[str, tuple[ImportedTeam, int | None]] = OrderedDict()
        self._registry = registry
        self._max = max_teams
        self._lock = RLock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._teams)

    def _keep(self, session_id: str, team: ImportedTeam) -> None:
        stamp = override_mtime(ROOT, team.entry_id)
        with self._lock:
            self._teams[session_id] = (team, stamp)
            self._teams.move_to_end(session_id)
            while len(self._teams) > self._max:
                self._teams.popitem(last=False)

    def add(self, team: ImportedTeam) -> str:
        session_id = uuid4().hex
        self._keep(session_id, team)
        self._registry.put(session_id, team.entry_id, team.horizon, team.risk_profile)
        return session_id

    def get(self, session_id: str) -> ImportedTeam:
        with self._lock:
            cached = self._teams.get(session_id)
            if cached is not None:
                self._teams.move_to_end(session_id)
        if cached is not None:
            team, stamp = cached
            current = override_mtime(ROOT, team.entry_id)
            if current == stamp:
                return team
            try:  # another session saved (or cleared) this entry's correction
                if current is None:
                    team = import_team(str(team.entry_id), ROOT, horizon=team.horizon, risk_profile=team.risk_profile)
                else:
                    team = replace(team, manual_changes=[])
                    load_team_override(ROOT, team)
            except AppError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            self._keep(session_id, team)
            return team
        pointer = self._registry.get(session_id)
        if pointer is None:
            raise HTTPException(status_code=404, detail="The team session does not exist. Please reload the team.")
        try:
            team = import_team(
                str(pointer.entry_id), ROOT, horizon=pointer.horizon, risk_profile=pointer.risk_profile,
            )
            load_team_override(ROOT, team)
        except AppError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        self._keep(session_id, team)
        return team

    def set(self, session_id: str, team: ImportedTeam) -> None:
        self._keep(session_id, team)
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
ANALYTICS = AnalyticsService(top_root=ROOT)
_STARTED_AT = time.time()
app = FastAPI(title="FPL Model API", version="1.0.0")


class TokenAuth:
    """Rejects requests without ``Authorization: Bearer <FPL_API_TOKEN>`` when a token is set.

    Plain ASGI rather than ``@app.middleware`` so the chat's event stream passes straight through.
    Added before CORS, so CORS wraps it and a 401 still carries CORS headers.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if (scope["type"] == "http" and API_TOKEN and scope["method"] != "OPTIONS"
                and scope["path"] != "/api/health"):
            sent = dict(scope["headers"]).get(b"authorization", b"")
            if not hmac.compare_digest(sent, f"Bearer {API_TOKEN}".encode()):
                response = JSONResponse({"detail": "Missing or wrong API token (FPL_API_TOKEN)."}, status_code=401)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


app.add_middleware(TokenAuth)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_origin_regex=os.environ.get("FPL_API_CORS_ORIGIN_REGEX"),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type", "Authorization"],
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


def _lineup_payload(lineup: dict) -> dict:
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
        "forecast_context": context(team),
        "chip_status": team.chip_status,
        "squad": _records(team.squad),
        "lineup": _lineup_payload(optimal_lineup(team.lineup_squad if team.lineup_squad is not None else team.squad)),
    }


def _as_http_error(exc: AppError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


RESULTS = ResultCache()


def _cached(team, endpoint: str, work, **options) -> dict:
    """T3/U10: answer from the cache when nothing that matters has changed."""
    key = cache_key(team, endpoint, **options)
    result, hit = RESULTS.compute(key, work)
    return {**result, "cache": {"key": key, "hit": hit, "computed_at": RESULTS.get(key)["computed_at"]}}


def _warm(team) -> None:
    """U10: compute the default strategy, one-transfer search and plan in the background."""
    requirements: tuple = ()
    RESULTS.warm([
        (cache_key(team, "strategy"), lambda: _json_safe(build_strategy_advice(team))),
        # The transfer page opens on min(2, max(1, FT)) transfers.
        (cache_key(team, "transfers", number=min(2, max(1, team.free_transfers)), outgoing=[]),
         lambda: _transfers_payload(team, min(2, max(1, team.free_transfers)), [])),
        (cache_key(team, "plan", weeks=team.horizon, discount=.9, chips=False, requirements=requirements),
         lambda: _json_safe(plan_with_context(team, weeks=team.horizon, discount=.9))),
        # W2: This week also shows chips and robustness.
        (cache_key(team, "chips"), lambda: _json_safe(recommend_chip_strategy(team))),
        (cache_key(team, "scenarios", scenarios=SCENARIOS), _scenarios_work(team, SCENARIOS)),
    ])


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - _STARTED_AT, 1),
        "active_sessions": len(STORE),
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
    _warm(team)
    return _team_payload(session_id, team)


@app.get("/api/team/{session_id}")
def get_team(session_id: str) -> dict:
    team = STORE.get(session_id)
    return _team_payload(session_id, team)


@app.patch("/api/team/{session_id}/settings")
def update_settings(session_id: str, request: TeamSettingsRequest) -> dict:
    current = STORE.get(session_id)
    team = replace(current, bank=request.bank, free_transfers=request.free_transfers,
                   team_value=int(current.squad["selling_price"].sum() + request.bank),
                   squad_source="manual_override")
    save_team_override(ROOT, team)
    STORE.set(session_id, team)
    _warm(team)
    return _team_payload(session_id, team)


@app.patch("/api/team/{session_id}/horizon")
def update_horizon(session_id: str, request: HorizonRequest) -> dict:
    try:
        updated = change_horizon(STORE.get(session_id), request.horizon)
        payload = _team_payload(session_id, updated)
    except AppError as exc:
        raise _as_http_error(exc) from exc
    STORE.set(session_id, updated)
    _warm(updated)
    return payload


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
    current = STORE.get(session_id)
    team = replace(current, manual_changes=list(current.manual_changes))  # changed below, stored only once saved
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
    STORE.set(session_id, team)
    _warm(team)
    payload = _team_payload(session_id, team)
    payload["squad_update"] = result
    return payload


@app.post("/api/team/{session_id}/squad/reset")
def reset_squad(session_id: str) -> dict:
    current = STORE.get(session_id)
    try:  # import first: if FPL is down, the correction stays
        team = import_team(
            str(current.entry_id), ROOT, horizon=current.horizon,
            risk_profile=current.risk_profile,
        )
    except AppError as exc:
        raise _as_http_error(exc) from exc
    clear_team_override(ROOT, current.entry_id)
    STORE.set(session_id, team)
    _warm(team)
    return _team_payload(session_id, team)


@app.post("/api/team/{session_id}/transfers")
def transfers(session_id: str, request: TransferRequest) -> dict:
    team = _constrained(STORE.get(session_id), request)
    try:
        return _cached(team, "transfers", lambda: _transfers_payload(team, request.number, request.outgoing_ids),
                       number=request.number, outgoing=sorted(request.outgoing_ids))
    except AppError as exc:
        raise _as_http_error(exc) from exc


def _transfers_payload(team, number: int, outgoing_ids: list[int]) -> dict:
    frame = recommend_transfers(team, number=number, forced_outgoing=outgoing_ids or None)
    return {
        "number": number,
        "outgoing_ids": outgoing_ids,
        "global_optimum": bool(not frame.empty and frame.iloc[0]["is_global_optimum"]),
        "plans": _records(frame),
    }


@app.post("/api/team/{session_id}/plan")
def multiweek_plan(session_id: str, request: PlanRequest) -> dict:
    team = _constrained(STORE.get(session_id), request)
    try:
        requirements = tuple(r.model_dump(exclude_none=True) for r in request.requirements)
        for requirement in requirements:
            needed = {"own_by": ("player_id", "event"), "sell_in": ("player_id", "event"),
                      "max_club": ("team_id", "limit"), "max_position": ("position", "limit")}[requirement["kind"]]
            if any(key not in requirement for key in needed):
                raise HTTPException(status_code=422, detail=f"{requirement['kind']} needs {', '.join(needed)}.")
        return _cached(team, "plan", lambda: _json_safe(plan_with_context(
            team, chips=request.chips, requirements=requirements, weeks=request.weeks, discount=request.discount)),
            weeks=request.weeks, discount=request.discount, chips=request.chips, requirements=requirements)
    except AppError as exc:
        raise _as_http_error(exc) from exc


@app.get("/api/team/{session_id}/market")
def market(
    session_id: str,
    position: str | None = Query(default=None, pattern="^(GK|DEF|MID|FWD)$"),
    max_price: int | None = Query(default=None, ge=30, le=200),
    limit: int = Query(default=20, ge=1, le=100),
    locked_ids: list[int] = Query(default=[], max_length=15),
    excluded_ids: list[int] = Query(default=[], max_length=800),
) -> dict:
    team = _constrained(STORE.get(session_id), ConstraintsRequest(locked_ids=locked_ids, excluded_ids=excluded_ids))
    frame = transfer_targets(team, position=position, max_price=max_price, limit=limit)
    return {"players": _records(frame)}


@app.get("/api/team/{session_id}/sells")
def sells(session_id: str, limit: int = Query(default=15, ge=1, le=15),
          locked_ids: list[int] = Query(default=[], max_length=15),
          excluded_ids: list[int] = Query(default=[], max_length=800)) -> dict:
    team = _constrained(STORE.get(session_id), ConstraintsRequest(locked_ids=locked_ids, excluded_ids=excluded_ids))
    return {"players": _records(sell_candidates(team, limit=limit))}


@app.post("/api/team/{session_id}/chips")
def chips(session_id: str, request: ConstraintsRequest = Body(default=ConstraintsRequest())) -> dict:
    team = _constrained(STORE.get(session_id), request)
    try:
        return _cached(team, "chips", lambda: _json_safe(recommend_chip_strategy(team)))
    except AppError as exc:
        raise _as_http_error(exc) from exc


@app.post("/api/team/{session_id}/recommended-squads")
def recommended_squads(session_id: str, request: ConstraintsRequest = Body(default=ConstraintsRequest())) -> dict:
    team = _constrained(STORE.get(session_id), request)
    try:
        return _json_safe(recommend_squads(team))
    except AppError as exc:
        raise _as_http_error(exc) from exc


@app.post("/api/team/{session_id}/strategy")
def strategy(session_id: str, request: ConstraintsRequest = Body(default=ConstraintsRequest())) -> dict:
    team = _constrained(STORE.get(session_id), request)
    try:
        return _cached(team, "strategy", lambda: _json_safe(build_strategy_advice(team)))
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


@app.get("/api/team/{session_id}/timeline")
def timeline(session_id: str) -> dict:
    team = STORE.get(session_id)
    try:
        return _json_safe(ANALYTICS.timeline(team.entry_id, ROOT / "data" / "local" / "cache"))
    except AppError as exc:
        raise _as_http_error(exc) from exc


@app.get("/api/team/{session_id}/shadow-summary")
def shadow_summary(session_id: str) -> dict:
    """L2: the model's shadow season for this team against what you actually scored, once rounds are scored."""
    team = STORE.get(session_id)
    states = sorted(ROOT.glob(f"artifacts/shadow_season/*_{team.entry_id}/state_gw*.json"),
                    key=lambda path: (path.parent.name, int(path.stem.split("gw")[1])))
    if not states:
        return {"available": False}
    state = json.loads(states[-1].read_text())
    first, through = int(state["first_event"]), int(state["next_event"]) - 1
    if through < first:
        return {"available": True, "first_event": first, "rounds": 0}
    endpoint = f"entry/{team.entry_id}/history/"
    try:
        history = ANALYTICS.many([endpoint])[endpoint]
    except AppError as exc:
        raise _as_http_error(exc) from exc
    yours = sum(int(row["points"]) - int(row.get("event_transfers_cost") or 0)
                for row in history.get("current", []) if first <= int(row["event"]) <= through)
    return {"available": True, "first_event": first, "through_event": through, "rounds": through - first + 1,
            "you": yours, "policies": {name: round(float(p["points"]), 1) for name, p in state["policies"].items()}}


@app.get("/api/team/{session_id}/top-managers")
def top_managers_view(
    session_id: str,
    cohort: str = Query(default="top100", pattern="^(top100|legacy|top1pct|youtubers)$"),
) -> dict:
    try:
        return _json_safe(top_managers.compare(STORE.get(session_id), cohort, ROOT))
    except AppError as exc:
        raise _as_http_error(exc) from exc


@app.get("/api/team/{session_id}/copy-check")
def copy_check_view(session_id: str, league_id: int | None = Query(default=None, gt=0)) -> dict:
    try:
        return _json_safe(copy_check.report(ROOT, STORE.get(session_id).entry_id, league_id))
    except AppError as exc:
        raise _as_http_error(exc) from exc


@app.get("/api/team/{session_id}/players/{player_id}")
def inspect_player(session_id: str, player_id: int) -> dict:
    try:
        return player_detail(STORE.get(session_id), player_id)
    except AppError as exc:
        raise _as_http_error(exc) from exc


@app.get("/api/team/{session_id}/changes")
def recent_changes(session_id: str) -> dict:
    payload = changes_since_previous(STORE.get(session_id), ROOT)
    return json.loads(json.dumps(payload, default=lambda v: v.item() if isinstance(v, np.generic) else str(v)))


@app.post("/api/team/{session_id}/compare")
def compare(session_id: str, request: CompareRequest) -> dict:
    try:
        return _json_safe(compare_players(_constrained(STORE.get(session_id), request), request.out_id, request.in_id))
    except AppError as exc:
        raise _as_http_error(exc) from exc


class BackgroundJob:
    """Runs one slow job at a time in a background thread; clients poll a status route.

    Used for the forecast refresh (live FPL API and optional paid sources, about
    a minute, shared by every session), the top-manager update (5-7 minutes)
    and the prospective loop. A start returns at once, so no HTTP request,
    proxy or phone has to stay open for the whole run. At most one run at a
    time, and ``min_interval`` seconds between starts so several clients
    tapping refresh don't hit the external sources over and over.
    """

    def __init__(self, job, label: str, min_interval: float = 30.0) -> None:
        self._job, self._label, self._min_interval = job, label, min_interval
        self._lock = RLock()
        self.state, self.error, self.result, self.started_at = "idle", None, None, None

    def start(self, job=None) -> None:
        with self._lock:
            if self.state == "running":
                raise HTTPException(status_code=409, detail=f"A {self._label} is already underway. Please try again.")
            if self.started_at is not None and time.time() - self.started_at < self._min_interval:
                wait = round(self._min_interval - (time.time() - self.started_at))
                raise HTTPException(status_code=429, detail=f"Wait {wait} seconds before the next {self._label}.")
            self.state, self.error, self.result, self.started_at = "running", None, None, time.time()
        Thread(target=self._work, args=(job or self._job,), daemon=True).start()

    def _work(self, job) -> None:
        try:
            result = job()
            with self._lock:
                self.state, self.result = "complete", json.loads(json.dumps(result, default=str))
        except Exception as exc:  # reported through the status route
            with self._lock:
                self.state, self.error = "failed", str(exc)

    def snapshot(self) -> dict:
        with self._lock:
            return {"state": self.state, "error": self.error, "result": self.result, "started_at": self.started_at,
                    "elapsed_seconds": round(time.time() - self.started_at) if self.started_at else 0}


def _refresh_and_lock():
    result = refresh_forecast(ROOT)
    _lock_if_due()
    return result


REFRESH_JOB = BackgroundJob(_refresh_and_lock, "forecast update")
TOP_JOB = BackgroundJob(lambda: top_managers.collect(ROOT), "top-manager update")
# Still manual: nothing schedules it. The loop itself refuses a second lock of the same round (plan O2).
LOOP_JOB = BackgroundJob(lambda: prospective_loop.auto(ROOT), "prospective loop run", min_interval=0)


@app.get("/api/top-managers/status")
def top_managers_status() -> dict:
    job = TOP_JOB.snapshot()
    return {"state": job["state"], "error": job["error"], **top_managers.PROGRESS}


@app.post("/api/team/{session_id}/top-managers/refresh", status_code=202)
def top_managers_refresh(session_id: str) -> dict:
    """Starts the update; progress and failures come from GET /api/top-managers/status."""
    entry = STORE.get(session_id).entry_id

    def job():
        top_managers.collect(ROOT)
        copy_check.collect(ROOT, entry)

    TOP_JOB.start(job)
    return {"status": "started"}


@app.get("/api/forecast/status")
def forecast_status() -> dict:
    job = REFRESH_JOB.snapshot()
    started = job["started_at"]
    result = {"state": job["state"], "error": job["error"], "elapsed_seconds": job["elapsed_seconds"],
              "stage": "Waiting for update", "captured": 0, "total": None}
    if result["state"] == "running":
        result["stage"] = "Downloading fixtures and source updates"
        paths = list((ROOT / 'data/raw/live_fpl').glob('capture_*/manifest.json'))
        paths = [p for p in paths if p.stat().st_mtime >= started]
        if paths:
            try:
                m = json.loads(max(paths, key=lambda p: p.stat().st_mtime).read_text())
                count = sum(k.startswith('player_') and v.get('status') == 200
                            for k, v in m.get('files', {}).items())
                result.update(captured=count, total=m.get('expected_players'))
                if count:
                    result['stage'] = 'Downloading player histories'
                if m.get('captured_players') or m.get('status') == 'complete':
                    result['stage'] = 'Generating and validating forecasts'
            except (OSError, ValueError):
                pass
    elif result['state'] == 'complete':
        result['stage'] = 'Forecast saved; reloading team'
    elif result['state'] == 'failed':
        result['stage'] = 'Update failed; previous forecasts retained'
    return result


@app.post("/api/forecast/refresh", status_code=202)
def refresh() -> dict:
    """Starts the forecast update; poll GET /api/forecast/status."""
    REFRESH_JOB.start()
    return {"status": "started"}


@app.post("/api/team/{session_id}/refresh", status_code=202)
def refresh_team(session_id: str) -> dict:
    """Starts the forecast update and then reloads this team; poll GET /api/forecast/status, then GET the team."""
    current = STORE.get(session_id)

    def job():
        refresh_forecast(ROOT)
        team = import_team(str(current.entry_id), ROOT, horizon=current.horizon, risk_profile=current.risk_profile)
        load_team_override(ROOT, team)
        STORE.set(session_id, team)
        _warm(team)
        _lock_if_due()

    REFRESH_JOB.start(job)
    return {"status": "started"}


def _loop_events() -> list[dict]:
    found = prospective_loop.captures(ROOT)
    if not found:
        return []
    return prospective_loop._gz(found[-1][0] / "bootstrap.json.gz")["events"]


def _loop_status() -> dict:
    return {**prospective_loop.status(ROOT, _loop_events()), "job": LOOP_JOB.snapshot(),
            "command": ".venv/bin/python src/prospective_loop.py auto", "fpl_data": fpl_data_freshness(ROOT)}


def _lock_if_due() -> None:
    """M16: a refresh inside the lock window also locks the round; the loop refuses a second lock."""
    try:
        current = _loop_status()
        if current["window_open"] and not current["locked"] and current["job"]["state"] != "running":
            LOOP_JOB.start()
    except Exception as exc:  # the forecast is saved either way; the lock banner still offers the lock
        print(f"Automatic lock skipped: {exc}")


@app.get("/api/loop/status")
def loop_status() -> dict:
    return _loop_status()


@app.post("/api/loop/lock")
def loop_lock() -> dict:
    current = _loop_status()
    if current["locked"]:
        raise HTTPException(status_code=409, detail=f"GW{current['event']} is already locked.")
    if not current["window_open"]:
        raise HTTPException(status_code=409, detail="The lock window is not open yet.")
    LOOP_JOB.start()
    return _loop_status()


@app.get("/api/data-quality")
def data_quality_report() -> dict:
    """Plan O3: source freshness, odds coverage, fallback share, ID coverage and their decision impact."""
    return _json_safe(data_quality.report(ROOT))


@app.get("/api/model-card")
def model_card() -> dict:
    """Plan E4: production model, locked-round results, calibration, limitations and data coverage."""
    return _json_safe(data_quality.model_card(ROOT))


@app.get("/api/team/{session_id}/lineup-value")
def lineup_autosub_value(session_id: str) -> dict:
    """Plan P3: XI forecast and the expectation including autosubs and vice-captain."""
    team = STORE.get(session_id)
    source = team.lineup_squad if team.lineup_squad is not None else team.squad
    return _json_safe(lineup_value(optimal_lineup(source)))


@app.get("/api/team/{session_id}/fixtures")
def fixtures(session_id: str, scope: str = Query(default="squad", pattern="^(squad|market)$"),
             limit: int = Query(default=30, ge=1, le=100)) -> dict:
    """U16: fixture ticker for your squad or the best players you do not own."""
    try:
        return _json_safe(fixture_ticker(STORE.get(session_id), scope, limit))
    except AppError as exc:
        raise _as_http_error(exc) from exc


SCENARIOS = 50


class ScenarioRequest(ConstraintsRequest):
    scenarios: int = Field(default=SCENARIOS, ge=20, le=100)


class BreakpointRequest(ConstraintsRequest):
    player_id: int = Field(gt=0)


@app.post("/api/team/{session_id}/scenarios")
def scenarios(session_id: str, request: ScenarioRequest) -> dict:
    """P5: hold vs plan A vs plan B on the same inputs, and how often each wins across sampled scenarios."""
    team = _constrained(STORE.get(session_id), request)
    try:
        return _cached(team, "scenarios", _scenarios_work(team, request.scenarios), scenarios=request.scenarios)
    except AppError as exc:
        raise _as_http_error(exc) from exc


def _scenarios_work(team, count: int):
    def work():
        plans = compare_plans(team)
        return _json_safe({"plans": plans, "robustness": robustness(team, plans, count),
                           "assumptions": team.scenario_overrides})
    return work


@app.post("/api/team/{session_id}/this-week")
def this_week(session_id: str, request: ConstraintsRequest = Body(default=ConstraintsRequest())) -> dict:
    """W1: the week's steps on one page, from the same cached results as Strategy, Chips and Scenarios."""
    team = _constrained(STORE.get(session_id), request)
    try:
        strategy = _cached(team, "strategy", lambda: _json_safe(build_strategy_advice(team)))
        lineup = lineup_after(team, strategy["plan"]["weeks"][0])
        chips = _cached(team, "chips", lambda: _json_safe(recommend_chip_strategy(team)))
    except AppError as exc:
        raise _as_http_error(exc) from exc
    try:
        robust = _cached(team, "scenarios", _scenarios_work(team, SCENARIOS), scenarios=SCENARIOS)["robustness"]
    except AppError:  # the week's plan still stands without the robustness share
        robust = None
    week = strategy["plan"]["weeks"][0]
    owned, market = team.squad.set_index("id"), team.market.drop_duplicates("id").set_index("id")
    sell = [{"id": i, "name": owned.at[i, "name"], "price": int(owned.at[i, "selling_price"])}
            for i in week.get("transfers_out_ids", [])]
    buy = [{"id": i, "name": market.at[i, "name"], "price": int(market.at[i, "price"])}
           for i in week.get("transfers_in_ids", [])]
    return _json_safe({"strategy": strategy, "lineup": _lineup_payload(lineup), "lineup_value": lineup_value(lineup),
                       "chips": chips, "robustness": robust, "sell": sell, "buy": buy})


@app.post("/api/team/{session_id}/scenarios/breakpoint")
def scenario_breakpoint(session_id: str, request: BreakpointRequest) -> dict:
    """P5: the chance of playing for one player at which the first-week action changes."""
    team = _constrained(STORE.get(session_id), request)
    try:
        return _cached(team, "breakpoint", lambda: _json_safe(breakpoint(team, request.player_id)), player=request.player_id)
    except AppError as exc:
        raise _as_http_error(exc) from exc


class JournalRequest(ConstraintsRequest):
    choice: str = Field(pattern="^(follow|roll|other)$")
    note: str = Field(default="", max_length=500)


@app.post("/api/team/{session_id}/journal")
def journal_record(session_id: str, request: JournalRequest) -> dict:
    """U19: freeze the current advice, the hold/A/B alternatives and your choice before the deadline."""
    team = _constrained(STORE.get(session_id), request)
    try:
        strategy = _cached(team, "strategy", lambda: _json_safe(build_strategy_advice(team)))
        strategy = {**strategy, "context": context(team)}
        alternatives = _cached(team, "scenarios-plans", lambda: {"plans": _json_safe(compare_plans(team))})["plans"]
        decision_journal.record(ROOT, team, strategy, alternatives, request.choice, request.note)
        return {"entries": decision_journal.entries(ROOT, decision_journal.season_of(team), team.entry_id)}
    except AppError as exc:
        raise _as_http_error(exc) from exc


@app.get("/api/team/{session_id}/journal")
def journal_entries(session_id: str) -> dict:
    team = STORE.get(session_id)
    return _json_safe({"entries": decision_journal.entries(ROOT, decision_journal.season_of(team), team.entry_id)})



# Context-aware chat (src/chat.py): Claude sees the forecast, the team, the page and calls these read-only tools.
CHATS = chat.ChatStore()
_CONSTRAINT_KEYS = ("locked_ids", "excluded_ids", "bench_weights", "overrides", "roll_margin", "max_hit")


class ChatRequest(ConstraintsRequest):
    message: str = Field(min_length=1, max_length=4000)
    # {view, label, calls: [{tool, args}], saved_plans: [...]} from the web page; summarised, never trusted as instructions.
    page: dict = Field(default_factory=dict)


_CHAT_SQUAD_COLUMNS = [
    "id", "name", "position", "team", "price", "selling_price", "purchase_price", "status", "news", "news_added",
    "availability", "opponent", "recommended_points", "recommended_q10", "recommended_q90", "decision_points",
    "expected_60plus_appearances", "form", "total_points", "selected_by_percent", "penalties_order",
    "price_change_projected_percent", "transfers_in_event", "transfers_out_event",
    "is_captain", "is_vice_captain", "multiplier",
]


def _chat_team_summary(session_id: str) -> dict:
    """The team payload without the columns the snapshot already has, and the lineup as ids and roles."""
    payload = get_team(session_id)
    payload["squad"] = [{k: row[k] for k in _CHAT_SQUAD_COLUMNS if k in row} for row in payload["squad"]]
    lineup = payload["lineup"]
    for part in ("starters", "bench"):
        lineup[part] = [{k: row.get(k) for k in ("id", "name", "position", "role", "is_captain", "is_vice_captain",
                                                  "recommended_points")} for row in lineup[part]]
    payload.pop("forecast_path", None)
    return payload


def _chat_tools(session_id: str, base: dict) -> dict:
    """The same route functions the pages call, with the user's preferences; nothing here writes."""
    def merged(args: dict) -> dict:
        result = dict(base)
        for key in ("locked_ids", "excluded_ids"):  # Claude's extra locks/exclusions add to the user's own
            if key in args:
                result[key] = sorted(set(base.get(key, [])) | set(args[key]))
        for key in ("overrides", "bench_weights"):  # a what-if replaces the user's own assumptions
            if key in args:
                result[key] = args[key]
        return result

    def own(args: dict) -> dict:
        return {key: value for key, value in args.items() if key not in _CONSTRAINT_KEYS}

    def ids(args: dict) -> dict:
        constraints = merged(args)
        return {"locked_ids": constraints.get("locked_ids", []), "excluded_ids": constraints.get("excluded_ids", [])}

    return {
        "team": lambda a: _chat_team_summary(session_id),
        "strategy": lambda a: strategy(session_id, ConstraintsRequest(**merged(a))),
        "transfers": lambda a: transfers(session_id, TransferRequest(**merged(a), **own(a))),
        "plan": lambda a: multiweek_plan(session_id, PlanRequest(**merged(a), **own(a))),
        "compare_players": lambda a: compare(session_id, CompareRequest(**merged(a), **own(a))),
        "player": lambda a: inspect_player(session_id, int(a["player_id"])),
        "market": lambda a: market(session_id, position=a.get("position"), max_price=a.get("max_price"),
                                   limit=a.get("limit", 20), **ids(a)),
        "sells": lambda a: sells(session_id, limit=15, **ids(a)),
        "chips": lambda a: chips(session_id, ConstraintsRequest(**merged(a))),
        "recommended_squads": lambda a: recommended_squads(session_id, ConstraintsRequest(**merged(a))),
        "scenarios": lambda a: scenarios(session_id, ScenarioRequest(**merged(a), **own(a))),
        "breakpoint": lambda a: scenario_breakpoint(session_id, BreakpointRequest(**merged(a), **own(a))),
        "fixtures": lambda a: fixtures(session_id, scope=a.get("scope", "squad"), limit=a.get("limit", 30)),
        "analytics": lambda a: analytics(session_id, event=a.get("event"), league_id=a.get("league_id")),
        "timeline": lambda a: timeline(session_id),
        "lineup_value": lambda a: lineup_autosub_value(session_id),
        "changes": lambda a: recent_changes(session_id),
        "journal": lambda a: journal_entries(session_id),
    }


def _chat_executor(tools: dict):
    def execute(name: str, args: dict) -> tuple[str, bool]:
        if name not in tools:
            return f"Unknown tool {name}.", True
        try:
            result = tools[name](args)
        except HTTPException as exc:
            return str(exc.detail), True
        except Exception as exc:  # invalid arguments or a failed calculation: Claude sees why
            return f"{type(exc).__name__}: {exc}", True
        if isinstance(result, dict):
            result = {key: value for key, value in result.items() if key != "cache"}
        return chat._dumps(result), False
    return execute


def _chat_sections(items: list[tuple[str, str, dict]], execute) -> str:
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda item: execute(item[1], item[2]), items))
    return "\n\n".join(f"## {title} [{name} {chat._dumps(args)}]\n{'ERROR: ' if failed else ''}{content}"
                       for (title, name, args), (content, failed) in zip(items, results))


def _chat_team_block(team, base: dict, saved_plans: list, execute) -> str:
    weeks = team.horizon
    items = [
        ("Team: squad, lineup, captain, chips and finances", "team", {}),
        ("Strategy centre", "strategy", {}),
        ("Transfer search (the Transfers page default)", "transfers", {"number": min(2, max(1, team.free_transfers))}),
        (f"Multiweek plan, {weeks} GW", "plan", {"weeks": weeks}),
        (f"Multiweek plan with chips, {weeks} GW", "plan", {"weeks": weeks, "chips": True}),
        ("Chip strategy", "chips", {}),
        ("Scenarios: hold vs plan A vs plan B", "scenarios", {}),
        ("Lineup value with autosubs", "lineup_value", {}),
        ("Changes since the previous snapshot", "changes", {}),
        ("Manager and mini-league analysis", "analytics", {}),
        ("Decision journal", "journal", {}),
    ]
    return ("<team_state>\nThe user's team, preferences and everything the app has computed for them now. "
            "This replaces any earlier <team_state>.\n"
            f"Preferences (locks, exclusions, own chance-of-playing assumptions, bench weights): {chat._dumps(base)}\n"
            f"Risk profile: {team.risk_profile}. Planning horizon: {weeks} GW. Target gameweek: GW{team.target_event}.\n"
            f"Saved plans: {chat._dumps(saved_plans)}\n\n{_chat_sections(items, execute)}\n</team_state>")


def _chat_page_block(view, label, calls: list[dict], execute) -> str:
    items = [(f"On the page: {call['tool']}", call["tool"], call.get("args") or {}) for call in calls]
    body = _chat_sections(items, execute) if items else "Nothing beyond the team state above."
    return f"<page>\nThe user is now looking at: {label or view} (page '{view}').\n{body}\n</page>"


@app.get("/api/team/{session_id}/chat")
def chat_history(session_id: str) -> dict:
    return {"messages": chat.transcript(CHATS.peek(session_id)), "enabled": chat.client(ROOT) is not None}


@app.post("/api/team/{session_id}/chat/reset")
def chat_reset(session_id: str) -> dict:
    CHATS.reset(session_id)
    return {"messages": []}


class NewsRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


_NEWS_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["players"], "properties": {"players": {
    "type": "array", "items": {"type": "object", "additionalProperties": False,
        "required": ["player_id", "chance", "status", "return_gw", "quote"],
        "properties": {"player_id": {"type": "integer"}, "chance": {"type": "number"},
                       "status": {"type": "string", "enum": ["out", "doubt", "available", "rested"]},
                       "return_gw": {"anyOf": [{"type": "integer"}, {"type": "null"}]}, "quote": {"type": "string"}}}}}}
_NEWS_SYSTEM = (
    "You turn football team news into chances of playing for Fantasy Premier League players. Use only the "
    "pasted text, never outside knowledge. Include only players the text is about and who appear in the "
    "player list; use their id from the list. chance is the probability (0 to 1) that the player appears in "
    "the next Gameweek. return_gw is the Gameweek the text says they return, or null. quote is the shortest "
    "phrase from the text that supports the estimate.")


@app.post("/api/team/{session_id}/news-assumptions")
def news_assumptions(session_id: str, request: NewsRequest) -> dict:
    """M20: pasted team news -> proposed chances of playing. Nothing is applied or stored; the user accepts
    each proposal into "Your assumptions" (overrides), and nothing is trained on."""
    api_client = chat.client(ROOT)
    if api_client is None:
        raise HTTPException(status_code=503, detail="Add ANTHROPIC_API_KEY to the .env file in the project folder to read team news.")
    team = STORE.get(session_id)
    market = team.market.drop_duplicates("id").set_index("id")
    players = "\n".join(f"{i}|{row['name']}|{row.get('team', '')}|{row['position']}" for i, row in market.iterrows())
    import anthropic
    try:
        response = api_client.messages.create(
            model=chat.MODEL, max_tokens=4000, system=_NEWS_SYSTEM,
            output_config={"effort": chat.EFFORT, "format": {"type": "json_schema", "schema": _NEWS_SCHEMA}},
            messages=[{"role": "user", "content": f"Next Gameweek: {team.target_event}\nPlayers (id|name|team|position):\n"
                                                  f"{players}\n\nTeam news:\n{request.text}"}])
    except anthropic.APIError as exc:
        raise HTTPException(status_code=502, detail=f"Claude could not read the news: {getattr(exc, 'message', exc)}") from exc
    if response.stop_reason != "end_turn":
        raise HTTPException(status_code=502, detail=f"Claude did not finish reading the news ({response.stop_reason}).")
    found = json.loads(next(block.text for block in response.content if block.type == "text"))["players"]
    proposals = {}
    for item in found:  # validated at the boundary: known players only, chance clamped, the last mention wins
        player_id = int(item["player_id"])
        if player_id not in market.index:
            continue
        row = market.loc[player_id]
        proposals[player_id] = {"player_id": player_id, "name": row["name"], "team": row.get("team", ""),
                                "chance": round(min(1.0, max(0.0, float(item["chance"]))), 2), "status": item["status"],
                                "return_gw": item["return_gw"], "quote": str(item["quote"])[:300],
                                "current_chance": float(row["availability"]) if pd.notna(row.get("availability")) else None}
    return _json_safe({"proposals": list(proposals.values())})


@app.post("/api/team/{session_id}/chat")
def chat_message(session_id: str, request: ChatRequest):
    """Streams the answer as server-sent events: status, text, notice, done or error."""
    api_client = chat.client(ROOT)
    if api_client is None:
        raise HTTPException(status_code=503, detail="Add ANTHROPIC_API_KEY to the .env file in the project folder to use the chat.")
    team = STORE.get(session_id)
    _constrained(team, request)  # reject invalid preferences before anything is sent
    base = request.model_dump(include=set(_CONSTRAINT_KEYS), exclude_none=True)
    page = request.page
    saved = page.get("saved_plans") if isinstance(page.get("saved_plans"), list) else []
    calls = [c for c in page.get("calls") or [] if isinstance(c, dict) and c.get("tool") in chat.TOOL_NAMES
             and isinstance(c.get("args", {}), dict)][:6]
    execute = _chat_executor(_chat_tools(session_id, base))
    conversation, replaced = CHATS.get(session_id, team, ROOT)
    team_sig = chat.signature(context(team)["revision"], base, saved)
    page_sig = chat.signature(page.get("view"), calls)

    def events():
        if replaced:
            yield chat.sse({"type": "notice", "text": "The forecast was updated, so a new chat started."})
        for event in chat.respond(
            conversation, api_client, request.message,
            team_sig, lambda: _chat_team_block(team, base, saved, execute),
            page_sig, lambda: _chat_page_block(page.get("view"), page.get("label"), calls, execute),
            execute,
        ):
            yield chat.sse(event)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
