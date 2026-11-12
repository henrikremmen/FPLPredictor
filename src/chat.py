"""Context-aware chat: Claude over the app's own forecasts, team and decision tools.

The prompt is append-only, so the prompt cache and preserved thinking stay
valid. The top-level system prompt (instructions + an 8-GW market snapshot +
model card) is frozen for the life of a conversation; a new forecast starts a
new conversation. Team state and page context arrive as mid-conversation
``role: "system"`` messages after the user's question, and only when they
change. Every tool is read-only and calls the same functions as the web pages.

ponytail: conversations live in memory and are lost when the API restarts.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
from threading import Lock
from typing import Callable, Iterator

import pandas as pd
from dotenv import dotenv_values

import data_quality
from decision_workspace import change_horizon
from fpl_app import AppError

MODEL = "claude-opus-5-5"  # supports the mid-conversation system messages below; Sonnet 5 does not
EFFORT = "low"  # Opus 5.5 defaults to medium
MAX_TOKENS = 64000
MAX_TOOL_ROUNDS = 10
MAX_CHATS = 16  # conversations kept in memory; the oldest is dropped beyond this
MIN_XP = 1.0  # players below this many expected points over the whole window are left out of the snapshot
# One hour, not five minutes: a manager pauses between questions, and a rewrite of ~80k tokens costs more
# than the 2x write price of the longer cache.
CACHE = {"type": "ephemeral", "ttl": "1h"}
# A classifier refusal reruns on Anthropic's recommended fallback model. Dropped for the rest of the
# process if the API rejects it for this model (its fallback targets were still open at launch).
FALLBACK = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}

INSTRUCTIONS = """You are the decision assistant inside the user's own Fantasy Premier League (FPL) model app. The user is a manager deciding transfers, captaincy, lineup, chips and plans. Act as a sharp sparring partner: help them reach a good decision, not just agree with them.

What you know
- <market_snapshot> below: the app's forecast for every player over the next gameweeks, a fixture grid per club, and the model card (how the model has done and its limits).
- <team_state> messages: the user's squad, bank, free transfers, chips, preferences and the main results the app has computed for them (strategy centre, transfer search, multiweek plans with and without chips, chip windows, scenarios, news changes, manager and mini-league analysis, journal, saved plans). The newest <team_state> is authoritative. Free Hit/Wildcard squads, the fixture ticker and the sell ranking are available through tools.
- <page> messages: the page the user is looking at and its results. "This", "these players" or "the plan" usually refers to what is on that page.
- Tools: the app's own optimiser and analysis, read-only. Use them whenever a question needs numbers you do not already have: a specific transfer, a replacement search, a plan with a requirement, a what-if on a player's chance of playing, a head-to-head comparison, a player's per-fixture detail.

How to work
- Never do the FPL arithmetic yourself when a tool can do it. Budget, selling prices, club limits, hits and lineup gains come from the tools. To judge "sell X", call transfers with outgoing_ids=[X] (and compare_players for a specific replacement).
- Quote numbers with their horizon: expected points (xP) over N gameweeks, and the q10-q90 range when risk matters. Say when a gain is small relative to the range.
- Weigh the whole picture: xP over the horizon, fixtures, minutes risk and news, captaincy (losing the captain matters), bench and autosubs, price changes, hits (-4 per transfer beyond the free ones), rolling a transfer (max 5 banked), chip timing, template and mini-league effects, and the user's risk profile.
- Be concrete: name players, gameweeks and numbers. Give a clear recommendation, the main reasons for and against, and what would change your mind. If the choice depends on the user's preference (risk, rank goal, chip plans), ask.
- If the data does not cover something, say so. Never invent statistics, prices or news.
- You cannot make transfers or change anything in the app. The user acts in FPL themselves.

Data notes
- Prices and bank are in tenths of a million: 158 = £15.8m. selling_price is what the user gets when selling.
- xP is expected FPL points from the app's model, already multiplied by the chance of playing. q10/q90 are the 10th and 90th percentile.
- Positions: GK, DEF, MID, FWD. Squad rules: 2 GK, 5 DEF, 5 MID, 3 FWD, at most 3 players per club.
- Player ids are the FPL element ids used by every tool.

Style
- Reply in the user's language (often Norwegian).
- Plain text with short paragraphs and simple "-" lists. No tables, no headings, at most a little **bold**.
- Lead with the answer, then the reasoning. Keep it as short as the question allows."""

TOOL_STATUS = {
    "analytics": "Reading manager and league analysis",
    "breakpoint": "Finding where the decision flips",
    "changes": "Checking changes since the last snapshot",
    "chips": "Planning chips",
    "compare_players": "Comparing the two players",
    "fixtures": "Reading the fixture ticker",
    "journal": "Reading the decision journal",
    "lineup_value": "Valuing the lineup with autosubs",
    "market": "Searching the market",
    "plan": "Running the multiweek planner",
    "player": "Reading the player detail",
    "recommended_squads": "Building Free Hit and Wildcard squads",
    "scenarios": "Comparing hold, plan A and plan B",
    "sells": "Ranking sell candidates",
    "strategy": "Reading the strategy centre",
    "timeline": "Reading the season timeline",
    "transfers": "Searching transfers",
}

_IDS = {"type": "array", "items": {"type": "integer"}}
_CONSTRAINTS = {
    "locked_ids": {**_IDS, "description": "Extra owned players to keep, added to the user's own locks."},
    "excluded_ids": {**_IDS, "description": "Extra players to leave out, added to the user's own exclusions."},
    "overrides": {
        "type": "array", "description": "What-if chance of playing (0-1) per player. Replaces the user's own assumptions.",
        "items": {"type": "object", "properties": {"player_id": {"type": "integer"}, "chance": {"type": "number"}},
                  "required": ["player_id", "chance"]},
    },
}


def _tool(name: str, description: str, properties: dict | None = None, required: list[str] | None = None,
          constraints: bool = False) -> dict:
    properties = {**(properties or {}), **(_CONSTRAINTS if constraints else {})}
    return {"name": name, "description": description,
            "input_schema": {"type": "object", "properties": properties, "required": required or []}}


TOOLS = sorted([
    _tool("strategy", "The strategy centre: roll or move this week, the best move per number of transfers, captain, news and chip hints.", constraints=True),
    _tool("transfers", "Exact search for the best legal transfer plans over the horizon (lineup gain, hit, bank after). Use outgoing_ids to force who is sold, e.g. to judge selling a specific player.",
          {"number": {"type": "integer", "minimum": 1, "maximum": 5, "description": "Number of transfers."},
           "outgoing_ids": {**_IDS, "description": "Owned players that must be sold (optional)."}}, ["number"], True),
    _tool("plan", "Multiweek transfer plan with rolling transfers and hits, optionally with chips and requirements.",
          {"weeks": {"type": "integer", "minimum": 1, "maximum": 8},
           "chips": {"type": "boolean", "description": "Also plan Bench Boost, Triple Captain, Free Hit and Wildcard."},
           "discount": {"type": "number", "minimum": 0.5, "maximum": 1, "description": "Weight per later week, default 0.9."},
           "requirements": {"type": "array", "description": "own_by/sell_in need player_id and event; max_club needs team_id and limit; max_position needs position and limit.",
                            "items": {"type": "object", "properties": {
                                "kind": {"type": "string", "enum": ["own_by", "sell_in", "max_club", "max_position"]},
                                "player_id": {"type": "integer"}, "event": {"type": "integer"}, "team_id": {"type": "integer"},
                                "position": {"type": "string", "enum": ["GK", "DEF", "MID", "FWD"]}, "limit": {"type": "integer"}},
                                "required": ["kind"]}}}, ["weeks"], True),
    _tool("compare_players", "Hold versus buy: an owned player against a same-position replacement, week by week, with bank, hit and risk.",
          {"out_id": {"type": "integer"}, "in_id": {"type": "integer"}}, ["out_id", "in_id"], True),
    _tool("player", "Full detail for one player: forecast per gameweek and per fixture, minutes probabilities, news and injury-return scenarios.",
          {"player_id": {"type": "integer"}}, ["player_id"]),
    _tool("market", "Best players the user does not own, ranked by the decision score, with optional position and price cap.",
          {"position": {"type": "string", "enum": ["GK", "DEF", "MID", "FWD"]},
           "max_price": {"type": "integer", "minimum": 30, "maximum": 200, "description": "Tenths of a million, e.g. 80 = £8.0m."},
           "limit": {"type": "integer", "minimum": 1, "maximum": 100}}, constraints=True),
    _tool("sells", "The user's players ranked from weakest to strongest over the horizon.", constraints=True),
    _tool("chips", "When to play each remaining chip, with the expected gain per window.", constraints=True),
    _tool("recommended_squads", "The best Free Hit squad per gameweek and the best Wildcard squad.", constraints=True),
    _tool("scenarios", "Hold versus plan A versus plan B on the same inputs, and how often each wins across sampled outcomes.",
          {"scenarios": {"type": "integer", "minimum": 20, "maximum": 100}}, constraints=True),
    _tool("breakpoint", "The chance of playing for one player at which this week's best action changes.",
          {"player_id": {"type": "integer"}}, ["player_id"], True),
    _tool("fixtures", "Fixture ticker with expected points per gameweek, for the squad or the best non-owned players.",
          {"scope": {"type": "string", "enum": ["squad", "market"]}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}),
    _tool("analytics", "Manager analysis: season log, one gameweek in detail, mini-league standings, effective ownership, rival differentials and risk.",
          {"event": {"type": "integer", "minimum": 1, "maximum": 38}, "league_id": {"type": "integer"}}),
    _tool("timeline", "Every played gameweek of the user's season: squad, captain, points and transfers."),
    _tool("lineup_value", "The XI forecast and the expectation including autosubs and the vice-captain."),
    _tool("changes", "What changed since the previous forecast snapshot: news, prices and forecasts."),
    _tool("journal", "The user's decision journal: earlier advice, alternatives and what they chose."),
], key=lambda tool: tool["name"])
TOOL_NAMES = {tool["name"] for tool in TOOLS}


def _dumps(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def signature(*parts) -> str:
    return hashlib.sha256(_dumps(parts).encode()).hexdigest()[:20]


def forecast_key(team) -> str:
    """A new capture or target gameweek means a new frozen system prompt, so a new conversation."""
    return f"{team.forecast_path}|{team.target_event}"


def _wide_weekly(team) -> pd.DataFrame:
    """Every gameweek the forecast covers (up to 8), independent of the user's planning horizon."""
    for weeks in range(8, team.horizon, -1):
        try:
            return change_horizon(team, weeks).weekly_market
        except AppError:
            continue
    return team.weekly_market if team.weekly_market is not None else team.market.assign(forecast_event=team.target_event)


def market_tables(weekly: pd.DataFrame) -> str:
    """A fixture grid per club and one CSV row per player with xP for every forecast gameweek."""
    events = sorted(int(e) for e in weekly["forecast_event"].unique())
    first = weekly[weekly["forecast_event"] == events[0]].set_index("id")
    keep = ["name", "position", "team", "price", "status", "news", "selected_by_percent", "form",
            "total_points", "penalties_order", "price_change_projected_percent"]
    players = first[[c for c in keep if c in first]].copy()
    if "news" in players:
        players["news"] = players["news"].fillna("").astype(str).str.slice(0, 90)
    if {"transfers_in_event", "transfers_out_event"} <= set(first):
        players["net_transfers_event"] = first["transfers_in_event"] - first["transfers_out_event"]
    xp = weekly.pivot_table(index="id", columns="forecast_event", values="recommended_points", aggfunc="sum")
    players = players.join(xp.round(1).rename(columns=lambda event: f"xp_gw{int(event)}"))
    players["xp_total"] = xp.sum(axis=1).round(1)
    for column, name in [("recommended_q10", "q10_total"), ("recommended_q90", "q90_total")]:
        if column in weekly:
            players[name] = weekly.groupby("id")[column].sum().round(1)
    for column, name in [("expected_60plus_appearances", "p60_avg"), ("market_player_goal_probability", "goal_p_avg"),
                         ("market_player_assist_probability", "assist_p_avg")]:
        if column in weekly:
            players[name] = weekly.groupby("id")[column].mean().round(2)
    left_out = int((players["xp_total"] < MIN_XP).sum())
    players = (players[players["xp_total"] >= MIN_XP].dropna(axis=1, how="all")
               .sort_values("xp_total", ascending=False).reset_index())

    grid = ""
    if {"team", "opponent"} <= set(weekly):
        clubs = weekly.groupby(["team", "forecast_event"])
        parts = [clubs["opponent"].first().unstack().rename(columns=lambda e: f"gw{int(e)}")]
        for column, name in [("market_team_expected_goals", "xg"), ("market_clean_sheet_probability", "cs")]:
            if column in weekly:
                parts.append(clubs[column].mean().round(2).unstack().rename(columns=lambda e, n=name: f"{n}_gw{int(e)}"))
        grid = pd.concat(parts, axis=1).dropna(axis=1, how="all").to_csv()
    return (f"Forecast gameweeks: {', '.join(f'GW{e}' for e in events)}.\n\n"
            f"Fixture grid per club (gwN = opponent, H/A; xg_gwN = club expected goals and cs_gwN = clean-sheet "
            f"probability from bookmaker odds where available):\n{grid}\n"
            f"Players ({len(players)} rows, sorted by xp_total; prices in tenths of a million; "
            f"xp_gwN is expected points in that gameweek; p60_avg is the mean probability of 60+ minutes; "
            f"{left_out} players with under {MIN_XP:g} xP over the whole window are left out - use the player "
            f"or market tool for them):\n"
            f"{players.to_csv(index=False)}")


_SNAPSHOTS: dict[str, str] = {}
_SNAPSHOT_LOCK = Lock()


def market_snapshot(team, root: Path) -> str:
    key = forecast_key(team)
    with _SNAPSHOT_LOCK:
        if key in _SNAPSHOTS:
            return _SNAPSHOTS[key]
    # Built outside the lock: it takes seconds, and other chats on the current snapshot should not wait.
    sections = [market_tables(_wide_weekly(team))]
    for title, build in [("Model card", data_quality.model_card), ("Data quality", data_quality.report)]:
        try:
            sections.append(f"{title}:\n{_dumps(build(root))}")
        except Exception as exc:  # the chat still works without them
            sections.append(f"{title}: unavailable ({exc})")
    snapshot = "<market_snapshot>\n" + "\n\n".join(sections) + "\n</market_snapshot>"
    with _SNAPSHOT_LOCK:
        if key not in _SNAPSHOTS:  # the first build wins, so every chat on this forecast caches the same prompt
            _SNAPSHOTS.clear()  # ponytail: one forecast at a time; key by forecast if several are served
            _SNAPSHOTS[key] = snapshot
        return _SNAPSHOTS[key]


def build_system(team, root: Path) -> list[dict]:
    return [{"type": "text", "text": INSTRUCTIONS},
            {"type": "text", "text": market_snapshot(team, root), "cache_control": CACHE}]


@dataclass
class Conversation:
    forecast_key: str
    system: list[dict]
    messages: list = field(default_factory=list)
    team_sig: str = ""
    page_sig: str = ""
    lock: Lock = field(default_factory=Lock)


class ChatStore:
    def __init__(self, max_chats: int = MAX_CHATS) -> None:
        self._items: OrderedDict[str, Conversation] = OrderedDict()
        self._max = max_chats
        self._lock = Lock()

    def get(self, session_id: str, team, root: Path) -> tuple[Conversation, bool]:
        """The session's conversation; a new forecast replaces it (its system prompt is frozen)."""
        key = forecast_key(team)
        with self._lock:
            current = self._items.get(session_id)
            if current is not None and current.forecast_key == key:
                self._items.move_to_end(session_id)
                return current, False
            self._items[session_id] = Conversation(key, build_system(team, root))
            self._items.move_to_end(session_id)
            while len(self._items) > self._max:
                self._items.popitem(last=False)
            return self._items[session_id], bool(current and current.messages)

    def peek(self, session_id: str) -> Conversation | None:
        with self._lock:
            return self._items.get(session_id)

    def reset(self, session_id: str) -> None:
        with self._lock:
            self._items.pop(session_id, None)


def transcript(conversation: Conversation | None) -> list[dict]:
    """The visible chat: the user's questions and Claude's text, one bubble per turn."""
    rows: list[dict] = []
    for message in conversation.messages if conversation else []:
        if message["role"] == "user" and isinstance(message["content"], str):
            rows.append({"role": "user", "text": message["content"]})
        elif message["role"] == "assistant":
            text = "".join(block.text for block in message["content"] if getattr(block, "type", "") == "text")
            if rows and rows[-1]["role"] == "assistant":
                rows[-1]["text"] += ("\n\n" if text and rows[-1]["text"] else "") + text
            else:
                rows.append({"role": "assistant", "text": text})
    return rows


_CLIENT, _KEY = None, None


def client(root: Path):
    """The Anthropic client for ANTHROPIC_API_KEY in .env (or the environment); .env is reread, so no restart."""
    global _CLIENT, _KEY
    key = (dotenv_values(root / ".env").get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not key:
        return None
    if key != _KEY:
        import anthropic
        _CLIENT, _KEY = anthropic.Anthropic(api_key=key), key
    return _CLIENT


def sse(event: dict) -> str:
    return f"data: {json.dumps(event, default=str)}\n\n"


def respond(conversation: Conversation, api, message: str, team_sig: str, team_block: Callable[[], str],
            page_sig: str, page_block: Callable[[], str], execute: Callable[[str, dict], tuple[str, bool]]) -> Iterator[dict]:
    """One user turn, all or nothing: on any failure the history is rolled back to before the question."""
    if not conversation.lock.acquire(blocking=False):
        yield {"type": "error", "message": "The chat is still answering. Wait for it to finish."}
        return
    start, signatures, completed = len(conversation.messages), (conversation.team_sig, conversation.page_sig), False
    usage = {"input_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0, "output_tokens": 0}
    try:
        conversation.messages.append({"role": "user", "content": message})
        blocks = []
        if team_sig != conversation.team_sig:
            yield {"type": "status", "text": "Collecting your team data"}
            blocks.append(team_block())
            conversation.team_sig = team_sig
        if page_sig != conversation.page_sig:
            blocks.append(page_block())
            conversation.page_sig = page_sig
        if blocks:  # must follow the user message: the cached history before it stays untouched
            conversation.messages.append({"role": "system", "content": "\n\n".join(blocks)})
        wrote_text, rounds = False, 0
        while rounds <= MAX_TOOL_ROUNDS:
            yield {"type": "status", "text": "Thinking"}
            separated = False
            try:
                stream = api.beta.messages.stream(
                    model=MODEL, max_tokens=MAX_TOKENS, system=conversation.system, tools=TOOLS,
                    messages=conversation.messages, thinking={"type": "adaptive"}, output_config={"effort": EFFORT},
                    cache_control=CACHE, **FALLBACK,
                ).__enter__()
            except Exception as exc:
                if FALLBACK and getattr(exc, "status_code", None) == 400 and "fallback" in str(exc).lower():
                    FALLBACK.clear()
                    continue
                raise
            rounds += 1
            with stream:
                for event in stream:
                    if event.type == "text" and event.text:
                        if wrote_text and not separated:
                            yield {"type": "text", "text": "\n\n"}
                        separated = wrote_text = True
                        yield {"type": "text", "text": event.text}
                    elif event.type == "content_block_start" and event.content_block.type == "tool_use":
                        yield {"type": "status", "text": TOOL_STATUS.get(event.content_block.name, "Working")}
                response = stream.get_final_message()
            for key in usage:
                usage[key] += getattr(response.usage, key, 0) or 0
            if response.stop_reason == "refusal":
                yield {"type": "error", "message": "Claude declined to answer this. Try rephrasing the question."}
                return
            tool_uses = [block for block in response.content if block.type == "tool_use"]
            if tool_uses and response.stop_reason == "max_tokens":
                yield {"type": "error", "message": "The answer was cut off. Try a narrower question."}
                return
            conversation.messages.append({"role": "assistant", "content": response.content})
            if not tool_uses:
                completed = True
                yield {"type": "done", "usage": usage}
                return
            results = []
            for block in tool_uses:
                content, failed = execute(block.name, block.input if isinstance(block.input, dict) else {})
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": content, "is_error": failed})
            conversation.messages.append({"role": "user", "content": results})
        yield {"type": "error", "message": f"Stopped after {MAX_TOOL_ROUNDS} rounds of tool calls. Try a narrower question."}
    except Exception as exc:  # reported in the chat; the history is rolled back below
        yield {"type": "error", "message": f"Chat failed: {exc}"}
    finally:
        if not completed:
            del conversation.messages[start:]
            conversation.team_sig, conversation.page_sig = signatures
        conversation.lock.release()
