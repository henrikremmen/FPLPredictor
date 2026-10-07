"""Streamlit interface for the read-only FPL decision engine."""

from __future__ import annotations

from datetime import datetime
from html import escape
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from fpl_app import (
    AppError,
    ImportedTeam,
    POSITION_ORDER,
    import_team,
    optimal_lineup,
    recommend_transfers,
    refresh_forecast,
    sell_candidates,
    transfer_targets,
)
from multiweek_planner import plan_multiweek


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEAM = "https://fantasy.premierleague.com/en/entry/5139814/event/4"
PROFILE_LABELS = {
    "Balanced – expected points": "balanced",
    "Stable – penalises wide uncertainty": "stable",
    "Upside – emphasises Q90": "upside",
}
STATUS_LABELS = {
    "a": "Available", "d": "Doubtful", "i": "Injured",
    "s": "Suspended", "u": "Unavailable", "n": "Not in the squad",
}


def _style() -> None:
    st.markdown(
        """
        <style>
        :root { --fpl-purple:#2b0a3d; --fpl-green:#00ff87; --fpl-pink:#e90052; }
        .stApp { background: linear-gradient(160deg, #faf8fc 0%, #f3f7f5 100%); }
        .block-container { max-width: 1280px; padding-top: 1.7rem; }
        [data-testid="stSidebar"] { background: #210833; color: white; }
        [data-testid="stSidebar"] label, [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3 { color: white; }
        .hero { padding: 1.4rem 1.6rem; border-radius: 20px; color: white;
            background: linear-gradient(115deg, #260638 0%, #5b146f 68%, #e90052 135%);
            box-shadow: 0 14px 35px rgba(43,10,61,.18); margin-bottom: 1.2rem; }
        .hero h1 { margin: 0; font-size: 2.05rem; }
        .hero p { margin: .35rem 0 0; color: #e9dff0; }
        .player-card { background: white; border: 1px solid #e8e0ec; border-top: 4px solid #00c875;
            border-radius: 13px; padding: .75rem .7rem; min-height: 108px; text-align: center;
            box-shadow: 0 5px 16px rgba(43,10,61,.07); margin-bottom: .7rem; }
        .player-card.captain { border-top-color: #e90052; }
        .player-card.vice { border-top-color: #6f42c1; }
        .player-name { font-weight: 750; color: #2b0a3d; line-height: 1.15; }
        .player-meta { color: #6f6575; font-size: .78rem; margin-top: .28rem; }
        .role { display:inline-block; color:white; background:#e90052; border-radius:999px;
            padding:.08rem .4rem; font-size:.7rem; font-weight:800; margin-left:.25rem; }
        .role.vc { background:#6f42c1; }
        .transfer-hero { background:white; border-left:5px solid #00c875; border-radius:12px;
            padding:1rem 1.15rem; box-shadow:0 5px 16px rgba(43,10,61,.07); margin:.6rem 0 1rem; }
        .muted { color:#6f6575; font-size:.88rem; }
        div[data-testid="stMetric"] { background:white; border:1px solid #e8e0ec;
            padding:.7rem 1rem; border-radius:14px; box-shadow:0 4px 14px rgba(43,10,61,.05); }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _deadline_label(value: str) -> str:
    timestamp = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(timestamp):
        return str(value)
    return timestamp.tz_convert("Europe/Oslo").strftime("%d %b %Y at %H:%M")


def _forecast_label(team: ImportedTeam) -> str:
    manifest_path = team.forecast_path.parent / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text())
        stamp = pd.to_datetime(manifest.get("forecast_at"), utc=True, errors="coerce")
        if pd.notna(stamp):
            return stamp.tz_convert("Europe/Oslo").strftime("%d.%m.%Y %H:%M")
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return datetime.fromtimestamp(team.forecast_path.stat().st_mtime).strftime("%d.%m.%Y %H:%M")


def player_table(frame: pd.DataFrame, team: ImportedTeam,
                 price_column: str | None = None) -> pd.DataFrame:
    """Create a compact English display frame without mutating model data."""
    if frame.empty:
        return pd.DataFrame()
    ordered = frame.copy()
    if "position" in ordered:
        ordered["_position_order"] = ordered["position"].map(POSITION_ORDER)
        score = "decision_points" if "decision_points" in ordered else "recommended_points"
        ordered = ordered.sort_values(["_position_order", score], ascending=[True, False])
    shown = pd.DataFrame(index=ordered.index)
    mappings = [
        ("position", "Pos"), ("name", "Player"), ("team", "Team"),
        ("opponent", "Opponent"),
    ]
    for source, label in mappings:
        if source in ordered:
            shown[label] = ordered[source]
    if price_column and price_column in ordered:
        shown["Price (£m)"] = ordered[price_column].astype(float) / 10
    if "recommended_points" in ordered:
        shown["Expected"] = ordered["recommended_points"].astype(float).round(2)
    if team.risk_profile != "balanced" and "decision_points" in ordered:
        shown["Profile score"] = ordered["decision_points"].astype(float).round(2)
    if "expected_60plus_appearances" in ordered and ordered["expected_60plus_appearances"].notna().any():
        values = ordered["expected_60plus_appearances"].astype(float)
        shown["P(60+)" if team.horizon == 1 else "Expected 60+"] = (
            (100 * values).round(0) if team.horizon == 1 else values.round(2)
        )
    if "point_range_q10_q90" in ordered and ordered["point_range_q10_q90"].notna().any():
        shown["Q10–Q90"] = ordered["point_range_q10_q90"]
    if "status" in ordered:
        shown["Status"] = ordered["status"].map(STATUS_LABELS).fillna(ordered["status"])
    if "role" in ordered:
        shown["Role"] = ordered["role"]
    if "bench_order" in ordered:
        shown.insert(0, "Bench", ordered["bench_order"])
    return shown.reset_index(drop=True)


def transfer_table(frame: pd.DataFrame, team: ImportedTeam) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    shown = pd.DataFrame({
        "Sell": frame["out"], "Buy": frame["in"],
        "Purchase price (£m)": frame["cost"].round(1),
        "Remaining (£m)": frame["money_left"].round(1),
        "Expected gain": frame["expected_gain"].round(2),
    })
    if team.risk_profile != "balanced":
        shown["Profile gain"] = frame["lineup_gain"].round(2)
    shown["Hit"] = frame["hit"].astype(int)
    shown["Net"] = frame["net_gain"].round(2)
    shown["Global optimum"] = frame["is_global_optimum"].map({True: "Yes", False: "Alternativ"})
    return shown


def _player_card(row: pd.Series) -> str:
    role = str(row.get("role", ""))
    card_class = "captain" if role == "C" else "vice" if role == "VC" else ""
    role_html = ""
    if role:
        role_class = "vc" if role == "VC" else ""
        role_html = f'<span class="role {role_class}">{escape(role)}</span>'
    score = float(row.get("recommended_points", 0))
    return (
        f'<div class="player-card {card_class}">'
        f'<div class="player-name">{escape(str(row["name"]))}{role_html}</div>'
        f'<div class="player-meta">{escape(str(row["team"]))} · {escape(str(row.get("opponent", "")))}</div>'
        f'<div class="player-meta"><b>{score:.2f}</b> expected points</div>'
        "</div>"
    )


def _render_formation(starters: pd.DataFrame) -> None:
    for position in ["FWD", "MID", "DEF", "GK"]:
        group = starters[starters["position"].eq(position)]
        if group.empty:
            continue
        left, middle, right = st.columns([1, max(len(group), 1) * 1.35, 1])
        with middle:
            columns = st.columns(len(group))
            for column, (_, row) in zip(columns, group.iterrows()):
                column.markdown(_player_card(row), unsafe_allow_html=True)


def _render_header(team: ImportedTeam) -> None:
    target = (f"GW{team.target_event}" if team.horizon == 1 else
              f"GW{team.target_event}–{team.target_event + team.horizon - 1}")
    st.markdown(
        f'<div class="hero"><h1>{escape(team.team_name)}</h1>'
        f'<p>{escape(team.manager_name)} · Forecast horizon {target} · '
        f'{escape(team.risk_profile)}</p></div>',
        unsafe_allow_html=True,
    )
    columns = st.columns(5)
    columns[0].metric("Bank", f"£{team.bank / 10:.1f}m")
    columns[1].metric("Free transfers", f"ca. {team.free_transfers}")
    columns[2].metric("Next GW", team.target_event)
    columns[3].metric("Deadline", _deadline_label(team.deadline).split(" at")[0])
    columns[4].metric("Forecast from", _forecast_label(team))


def _render_overview(team: ImportedTeam) -> None:
    left, right = st.columns([1.55, 1])
    with left:
        st.subheader("Your squad")
        table = player_table(team.squad, team, "selling_price")
        st.dataframe(table, hide_index=True, width="stretch")
        st.download_button(
            "Download squad as CSV", table.to_csv(index=False).encode("utf-8"),
            file_name=f"fpl_squad_{team.entry_id}.csv", mime="text/csv",
        )
    with right:
        st.subheader("Model points")
        chart = (team.squad[["name", "recommended_points"]]
                 .sort_values("recommended_points", ascending=False)
                 .set_index("name"))
        st.bar_chart(chart, color="#5b146f", height=430)
        st.info(
            "Selling prices and free transfers are estimated from public history. "
            "Correct them in the side panel if the FPL shows other numbers."
        )


def _render_lineup(team: ImportedTeam) -> None:
    source = team.lineup_squad if team.lineup_squad is not None else team.squad
    lineup = optimal_lineup(source)
    first, second, third = st.columns(3)
    first.metric("Formation", lineup["formation"])
    second.metric("Expected including Captain", f'{lineup["expected_total"]:.2f}')
    third.metric("C/VC-margin", f'{lineup["captain_margin"]:.2f}')
    if lineup["captain_margin"] < .5:
        st.warning("The captain choice has low model margin. Treat C/VC as an uncertain choice.")
    _render_formation(lineup["starters"])
    st.subheader("Bench")
    st.dataframe(player_table(lineup["bench"], team), hide_index=True, width="stretch")


def _transfer_key(team: ImportedTeam, number: int) -> tuple:
    return (
        team.entry_id, team.event, team.target_event, team.horizon,
        team.risk_profile, team.bank, team.free_transfers, number,
        str(team.forecast_path),
    )


def _render_transfers(team: ImportedTeam) -> None:
    st.subheader("Transfer plan")
    st.caption("Choose the number of transfers. The calculation uses the selected horizon and risk profile.")
    number = st.radio("Number of transfers", [1, 2, 3, 4, 5], horizontal=True, key="transfer_count")
    key = _transfer_key(team, int(number))
    cache = st.session_state.setdefault("transfer_results", {})
    if st.button("Calculate best plan", type="primary", width="stretch"):
        with st.spinner("Searching legal transfers…"):
            cache[key] = recommend_transfers(team, number=int(number))
    suggestions = cache.get(key)
    if suggestions is None:
        st.info("Click \"Calculate best plan\" to start the search.")
        return
    if suggestions.empty:
        st.warning("No feasible plan was found for this number of transfers.")
        return
    best = suggestions.iloc[0]
    verdict = "The model prefers to roll the transfer" if best["net_gain"] <= 0 else "Best plan"
    st.markdown(
        f'<div class="transfer-hero"><b>{escape(verdict)}</b><br>'
        f'{escape(str(best["out"]))} &nbsp;→&nbsp; {escape(str(best["in"]))}<br>'
        f'<span class="muted">Net model gain {float(best["net_gain"]):.2f} · '
        f'rest £{float(best["money_left"]):.1f}m · hit {int(best["hit"])}</span></div>',
        unsafe_allow_html=True,
    )
    table = transfer_table(suggestions, team)
    st.dataframe(table, hide_index=True, width="stretch")
    st.download_button(
        "Download suggestions as CSV", table.to_csv(index=False).encode("utf-8"),
        file_name=f"fpl_transfer_strategy_{team.entry_id}.csv", mime="text/csv",
    )
    if int(number) >= 2:
        suffix = "; the other rows are broad backup options" if int(number) == 2 else ""
        st.caption(f"The proposal is globally optimal{suffix}.")


def _render_multiweek(team: ImportedTeam) -> None:
    st.subheader("Multiweek plan")
    st.caption(
        "Optimises transfers, rolling free transfers, starting XIs and captains together."
    )
    key = (*_transfer_key(team, 0), "multiweek")
    cache = st.session_state.setdefault("multiweek_results", {})
    if st.button("Calculate multiweek plan", type="primary", width="stretch"):
        try:
            with st.spinner("Solving the full planning horizon…"):
                cache[key] = plan_multiweek(team, weeks=team.horizon)
        except AppError as exc:
            st.error(str(exc))
    result = cache.get(key)
    if result is None:
        st.info("Click \"Calculate multiweek plan\" to start optimisation.")
        return
    first, second = st.columns(2)
    first.metric("Projected total", f'{result["total_projected_points"]:.2f}')
    second.metric("Gameweeks", len(result["weeks"]))
    for week in result["weeks"]:
        with st.expander(
            f'GW{week["event"]} · {week["formation"]} · '
            f'{week["projected_points"]:.2f} points', expanded=True
        ):
            outgoing = ", ".join(week["transfers_out"]) or "None"
            incoming = ", ".join(week["transfers_in"]) or "None"
            st.markdown(
                f'**OUT:** {outgoing}  \n**IN:** {incoming}  \n'
                f'**Captain:** {week["captain"]} · **Bank:** £{week["bank"]:.1f}m · '
                f'**FT before round:** {week["free_transfers_before"]} · '
                f'**Hit:** −{week["hit"]}'
            )
            st.caption("Starting XI: " + " · ".join(week["starters"]))
    st.warning(result["caveat"])


def _render_market(team: ImportedTeam) -> None:
    buy_tab, sell_tab = st.tabs(["Buy candidates", "Sell candidates"])
    with buy_tab:
        first, second, third = st.columns(3)
        position = first.selectbox("Position", ["All", "GK", "DEF", "MID", "FWD"])
        maximum = second.number_input(
            "Maximum price (£m)", min_value=3.0,
            max_value=float(team.market["price"].max() / 10),
            value=float(team.market["price"].max() / 10), step=.1,
        )
        limit = third.slider("Number of candidates", 5, 30, 12)
        targets = transfer_targets(
            team, None if position == "All" else position,
            max_price=round(maximum * 10), limit=limit,
        )
        st.dataframe(player_table(targets, team, "price"), hide_index=True, width="stretch")
    with sell_tab:
        sells = sell_candidates(team, limit=15)
        st.caption("Lowest model scores first. These are candidates to review, not automatic sales.")
        st.dataframe(player_table(sells, team, "selling_price"), hide_index=True, width="stretch")


def _render_method(team: ImportedTeam) -> None:
    st.subheader("What the app does")
    st.markdown(
        """
        Reads only public FPL data and never makes transfers on your account. Selects a legal XI, captain, vice-captain and bench order. Checks budget, positions, club limits, selling prices and hits. Transfers and multiweek plans are optimised globally across the market for 1–8 Gameweeks. `stable` and `upside` are experimental utility profiles; `balanced` is the default.
        """
    )
    st.warning(
        "The model is a decision tool, not a guarantee. Injury and team news are not fully "
        "modelled, and public team data only provide estimated free transfers and selling prices."
    )
    st.code(str(team.forecast_path), language=None)


def _load_team(reference: str, horizon: int, profile: str) -> ImportedTeam | None:
    try:
        with st.spinner("Importing your team and loading its model forecast…"):
            return import_team(reference, ROOT, horizon=horizon, risk_profile=profile)
    except AppError as exc:
        st.error(str(exc))
        return None


def _sidebar() -> ImportedTeam | None:
    st.sidebar.title("FPL Model")
    st.sidebar.caption("Read-only decision support")
    with st.sidebar.form("team_form"):
        reference = st.text_input("Team URL or team ID", value=DEFAULT_TEAM)
        horizon = st.select_slider("Forecast horizon", options=list(range(1, 9)), value=3,
                                   format_func=lambda value: f"{value} GW")
        profile_label = st.selectbox("Risk profile", list(PROFILE_LABELS))
        submitted = st.form_submit_button("Load team", type="primary", width="stretch")
    profile = PROFILE_LABELS[profile_label]
    if submitted:
        loaded = _load_team(reference, int(horizon), profile)
        if loaded is not None:
            st.session_state["team"] = loaded
            st.session_state["load_version"] = st.session_state.get("load_version", 0) + 1
            st.session_state["load_settings"] = (reference, int(horizon), profile)
            st.session_state["transfer_results"] = {}
            st.session_state["multiweek_results"] = {}

    st.sidebar.divider()
    if st.sidebar.button("Refresh forecast", width="stretch"):
        try:
            with st.spinner("Getting a new public snapshot. This can take about a minute..."):
                refresh_forecast(ROOT)
            settings = st.session_state.get("load_settings", (reference, int(horizon), profile))
            loaded = _load_team(*settings)
            if loaded is not None:
                st.session_state["team"] = loaded
                st.session_state["load_version"] = st.session_state.get("load_version", 0) + 1
                st.session_state["transfer_results"] = {}
                st.session_state["multiweek_results"] = {}
                st.sidebar.success("The forecast is up to date.")
        except AppError as exc:
            st.sidebar.error(str(exc))

    team = st.session_state.get("team")
    if team is not None:
        version = st.session_state.get("load_version", 0)
        with st.sidebar.expander("Adjust public estimates"):
            bank = st.number_input(
                "Bank (£m)", min_value=0.0, max_value=20.0,
                value=float(team.bank / 10), step=.1, key=f"bank_{version}",
            )
            free_transfers = st.number_input(
                "Free transfers", min_value=0, max_value=5,
                value=int(team.free_transfers), step=1, key=f"ft_{version}",
            )
            corrected_bank = round(float(bank) * 10)
            corrected_ft = int(free_transfers)
            if corrected_bank != team.bank or corrected_ft != team.free_transfers:
                team.bank = corrected_bank
                team.free_transfers = corrected_ft
                st.session_state["transfer_results"] = {}
                st.session_state["multiweek_results"] = {}
            st.caption("Use the numbers displayed inside the FPL if they differ.")
        st.sidebar.caption(f"Forecast: {_forecast_label(team)}")
    st.sidebar.caption("The app never logs in or changes your team.")
    return team


def main() -> None:
    st.set_page_config(
        page_title="FPL Model", page_icon="⚽", layout="wide",
        initial_sidebar_state="expanded",
    )
    _style()
    team = _sidebar()
    if team is None:
        st.markdown(
            '<div class="hero"><h1>FPL Model</h1>'
            '<p>From a public team link to a starting XI, captain and transfer plan.</p></div>',
            unsafe_allow_html=True,
        )
        st.subheader("Get started")
        st.markdown(
            "1. Paste the FPL link into the side panel.\n"
            "2. Choose 1-8 Gameweeks and Risk Profile.\n"
            "3. Click **Load team**."
        )
        st.info("The example link of your team is already filled in.")
        return

    _render_header(team)
    overview, lineup, transfers, multiweek, market, method = st.tabs([
        "Overview", "Starting XI", "Transfers", "Multiweek plan", "Market", "About the model",
    ])
    with overview:
        _render_overview(team)
    with lineup:
        _render_lineup(team)
    with transfers:
        _render_transfers(team)
    with multiweek:
        _render_multiweek(team)
    with market:
        _render_market(team)
    with method:
        _render_method(team)


if __name__ == "__main__":
    main()
