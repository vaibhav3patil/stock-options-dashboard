"""Presentation helpers for the Streamlit option-buying desk."""

from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any, Optional

import pandas as pd
import streamlit as st

from app.models.schemas import Eligibility, SymbolRow

ELIGIBILITY_LABELS = {
    Eligibility.NAKED_BUY_OK.value: "Ready to buy",
    Eligibility.SPREAD_ONLY.value: "Spread only",
    Eligibility.WATCH.value: "Watch",
    Eligibility.EXCLUDE.value: "Skip",
}

ELIGIBILITY_HELP = {
    Eligibility.NAKED_BUY_OK.value: "Passed liquidity + move vs premium. Naked CE/PE buy is allowed.",
    Eligibility.SPREAD_ONLY.value: "Direction ok, but IV looks rich — prefer a debit spread.",
    Eligibility.WATCH.value: "Incomplete setup or missing move. Idea is tentative.",
    Eligibility.EXCLUDE.value: "Failed hard gates. Do not buy.",
}

ELIGIBILITY_COLORS = {
    Eligibility.NAKED_BUY_OK.value: "rgba(61, 220, 151, 0.16)",
    Eligibility.SPREAD_ONLY.value: "rgba(245, 193, 74, 0.16)",
    Eligibility.WATCH.value: "rgba(125, 211, 252, 0.12)",
    Eligibility.EXCLUDE.value: "rgba(255, 107, 122, 0.14)",
}

RULE_LABELS = {
    "IN12": "Data freshness",
    "L1-L5": "Option liquidity",
    "M3": "Move vs premium",
    "V5": "IV vs historical vol",
    "T1": "Trend / direction",
    "T2": "Relative strength vs Nifty",
    "T4": "Squeeze / coil",
    "P5": "Put–call OI (PCR)",
    "IN10": "Premium per lot budget",
    "Eligibility": "Buy readiness",
    "IN1": "F&O ban list",
    "C1": "Earnings / event window",
    "V3-V4": "IV Rank / Percentile",
}

APP_CSS = """
<style>
    .block-container { padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1400px; }
    [data-testid="stSidebar"] { background: linear-gradient(180deg, #0B1220 0%, #10192B 100%); }

    .hero {
        background: linear-gradient(135deg, #12203A 0%, #0E2A28 55%, #151D2E 100%);
        border: 1px solid #2A3550;
        border-radius: 16px;
        padding: 1.15rem 1.35rem 1.05rem;
        margin-bottom: 1rem;
    }
    .hero-kicker {
        color: #3DDC97;
        font-size: 0.78rem;
        letter-spacing: 0.12em;
        font-weight: 600;
        text-transform: uppercase;
        margin-bottom: 0.25rem;
    }
    .hero h1 {
        margin: 0;
        font-size: 1.7rem;
        font-weight: 700;
        color: #F4F7FB;
    }
    .hero p {
        margin: 0.35rem 0 0;
        color: #A8B4C8;
        font-size: 0.95rem;
    }

    .idea-card {
        border-radius: 16px;
        padding: 1.15rem 1.25rem;
        border: 1px solid #2A3550;
        margin: 0.4rem 0 0.8rem;
    }
    .idea-card.call {
        background: linear-gradient(135deg, rgba(61,220,151,0.14), rgba(21,29,46,0.9));
        border-color: rgba(61,220,151,0.35);
    }
    .idea-card.put {
        background: linear-gradient(135deg, rgba(255,107,122,0.14), rgba(21,29,46,0.9));
        border-color: rgba(255,107,122,0.35);
    }
    .idea-card.none {
        background: #151D2E;
    }
    .idea-kicker {
        font-size: 0.75rem;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        font-weight: 600;
        color: #94A3B8;
        margin-bottom: 0.3rem;
    }
    .idea-title {
        font-size: 1.35rem;
        font-weight: 700;
        color: #F4F7FB;
        margin-bottom: 0.35rem;
    }
    .idea-sub { color: #C5D0E0; font-size: 0.95rem; line-height: 1.45; }

    .chip-row { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.55rem 0 0.2rem; }
    .chip {
        display: inline-block;
        padding: 0.18rem 0.55rem;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 600;
        background: #1C2740;
        color: #D7E0EE;
        border: 1px solid #2A3550;
    }
    .chip.ok { background: rgba(61,220,151,0.15); color: #3DDC97; border-color: rgba(61,220,151,0.3); }
    .chip.warn { background: rgba(245,193,74,0.15); color: #F5C14A; border-color: rgba(245,193,74,0.3); }
    .chip.bad { background: rgba(255,107,122,0.15); color: #FF6B7A; border-color: rgba(255,107,122,0.3); }
    .chip.info { background: rgba(125,211,252,0.12); color: #7DD3FC; border-color: rgba(125,211,252,0.28); }
    .chip.violet { background: rgba(167,139,250,0.16); color: #C4B5FD; border-color: rgba(167,139,250,0.35); }

    .hint {
        color: #94A3B8;
        font-size: 0.86rem;
        margin-top: 0.35rem;
    }
    .section-title {
        font-size: 1.15rem;
        font-weight: 700;
        margin: 0.4rem 0 0.15rem;
    }
    .prio-grid {
        display: grid;
        grid-template-columns: repeat(5, minmax(0, 1fr));
        gap: 0.65rem;
        margin: 0.5rem 0 0.9rem;
    }
    @media (max-width: 1200px) {
        .prio-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    }
    .prio-card {
        border-radius: 14px;
        padding: 0.85rem 1rem;
        border: 1px solid #2A3550;
        background: #151D2E;
        min-height: 128px;
        position: relative;
    }
    .prio-card.high { border-color: rgba(61,220,151,0.4); background: linear-gradient(180deg, rgba(61,220,151,0.12), #151D2E); }
    .prio-card.medium { border-color: rgba(245,193,74,0.35); background: linear-gradient(180deg, rgba(245,193,74,0.10), #151D2E); }
    .prio-card.low { border-color: rgba(255,107,122,0.3); }
    .prio-card.top5 {
        border-color: #F5C14A;
        box-shadow: 0 0 0 1px rgba(245,193,74,0.45), 0 8px 22px rgba(245,193,74,0.12);
        background: linear-gradient(180deg, rgba(245,193,74,0.18), rgba(61,220,151,0.08) 55%, #151D2E);
    }
    .prio-badge {
        position: absolute;
        top: 0.55rem;
        right: 0.55rem;
        background: #F5C14A;
        color: #1A1403;
        font-size: 0.68rem;
        font-weight: 700;
        letter-spacing: 0.04em;
        padding: 0.12rem 0.4rem;
        border-radius: 999px;
    }
    .prio-rank { font-size: 0.75rem; letter-spacing: 0.08em; text-transform: uppercase; color: #94A3B8; font-weight: 600; }
    .prio-sym { font-size: 1.15rem; font-weight: 700; color: #F4F7FB; margin: 0.15rem 0; padding-right: 3.2rem; }
    .prio-meta { color: #C5D0E0; font-size: 0.84rem; line-height: 1.4; }
    .mkt {
        border-radius: 14px;
        padding: 0.9rem 1.1rem;
        margin: 0.2rem 0 0.9rem;
        border: 1px solid rgba(245,193,74,0.35);
        background: linear-gradient(135deg, rgba(245,193,74,0.10), #151D2E 70%);
    }
    .mkt.RISK_ON { border-color: rgba(61,220,151,0.4); background: linear-gradient(135deg, rgba(61,220,151,0.10), #151D2E 70%); }
    .mkt.RISK_OFF { border-color: rgba(255,107,122,0.4); background: linear-gradient(135deg, rgba(255,107,122,0.10), #151D2E 70%); }
    .mkt-kicker { font-size: 0.72rem; letter-spacing: 0.1em; text-transform: uppercase; font-weight: 700; color: #F5C14A; }
    .mkt h3 { margin: 0.2rem 0 0.35rem; font-size: 1.05rem; color: #F4F7FB; }
    .mkt p { margin: 0.15rem 0; color: #C5D0E0; font-size: 0.9rem; line-height: 1.45; }

    .idea-panel { margin: 0.2rem 0 0.85rem; }
    .idea-row-title {
        font-size: 0.78rem; letter-spacing: 0.08em; text-transform: uppercase;
        font-weight: 700; color: #94A3B8; margin: 0.7rem 0 0.4rem;
    }
    .tile-grid {
        display: grid;
        grid-template-columns: repeat(6, minmax(0, 1fr));
        gap: 0.55rem;
    }
    .tile-grid.five { grid-template-columns: repeat(5, minmax(0, 1fr)); }
    .tile-grid.four { grid-template-columns: repeat(4, minmax(0, 1fr)); }
    @media (max-width: 1100px) {
        .tile-grid, .tile-grid.five, .tile-grid.four { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    .tile {
        border-radius: 14px;
        padding: 0.75rem 0.8rem 0.7rem;
        border: 1px solid #2A3550;
        background: #151D2E;
        min-height: 86px;
    }
    .tile .lbl { font-size: 0.72rem; letter-spacing: 0.06em; text-transform: uppercase; font-weight: 700; color: #94A3B8; }
    .tile .val { font-size: 1.18rem; font-weight: 700; color: #F4F7FB; margin-top: 0.2rem; line-height: 1.2; }
    .tile .sub { font-size: 0.75rem; color: #A8B4C8; margin-top: 0.18rem; }
    .tile.buy { background: linear-gradient(180deg, rgba(61,220,151,0.22), #151D2E); border-color: rgba(61,220,151,0.45); }
    .tile.buy .lbl, .tile.buy .val { color: #3DDC97; }
    .tile.sell { background: linear-gradient(180deg, rgba(125,211,252,0.20), #151D2E); border-color: rgba(125,211,252,0.45); }
    .tile.sell .lbl, .tile.sell .val { color: #7DD3FC; }
    .tile.stop { background: linear-gradient(180deg, rgba(255,107,122,0.20), #151D2E); border-color: rgba(255,107,122,0.45); }
    .tile.stop .lbl, .tile.stop .val { color: #FF6B7A; }
    .tile.gold { background: linear-gradient(180deg, rgba(245,193,74,0.20), #151D2E); border-color: rgba(245,193,74,0.45); }
    .tile.gold .lbl, .tile.gold .val { color: #F5C14A; }
    .tile.violet { background: linear-gradient(180deg, rgba(167,139,250,0.20), #151D2E); border-color: rgba(167,139,250,0.45); }
    .tile.violet .lbl, .tile.violet .val { color: #C4B5FD; }
    .tile.call { background: linear-gradient(180deg, rgba(61,220,151,0.16), #151D2E); border-color: rgba(61,220,151,0.35); }
    .tile.put { background: linear-gradient(180deg, rgba(255,107,122,0.16), #151D2E); border-color: rgba(255,107,122,0.35); }
    .tile.ok { background: linear-gradient(180deg, rgba(61,220,151,0.18), #151D2E); border-color: rgba(61,220,151,0.4); }
    .tile.ok .val { color: #3DDC97; }
    .tile.warn { background: linear-gradient(180deg, rgba(245,193,74,0.18), #151D2E); border-color: rgba(245,193,74,0.4); }
    .tile.warn .val { color: #F5C14A; }
    .tile.bad { background: linear-gradient(180deg, rgba(255,107,122,0.18), #151D2E); border-color: rgba(255,107,122,0.4); }
    .tile.bad .val { color: #FF6B7A; }

    .cmp-wrap { margin: 0.35rem 0 1rem; overflow-x: auto; }
    .cmp {
        width: 100%;
        border-collapse: separate;
        border-spacing: 0;
        min-width: 920px;
        background: #10192B;
        border: 1px solid #2A3550;
        border-radius: 16px;
        overflow: hidden;
    }
    .cmp th, .cmp td {
        padding: 0.55rem 0.7rem;
        text-align: center;
        border-bottom: 1px solid #243049;
        vertical-align: middle;
    }
    .cmp th.metric, .cmp td.metric {
        text-align: left;
        width: 8.2rem;
        color: #94A3B8;
        font-size: 0.72rem;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        font-weight: 700;
        background: #121A2C;
        position: sticky;
        left: 0;
        z-index: 1;
    }
    .cmp thead th.col {
        padding: 0.85rem 0.7rem 0.75rem;
        background: #151D2E;
        border-bottom: 1px solid #2A3550;
    }
    .cmp thead th.col.call { background: linear-gradient(180deg, rgba(61,220,151,0.16), #151D2E); }
    .cmp thead th.col.put { background: linear-gradient(180deg, rgba(255,107,122,0.16), #151D2E); }
    .cmp thead th.col.pick {
        box-shadow: inset 0 3px 0 #F5C14A;
    }
    .cmp .rank {
        font-size: 0.68rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        font-weight: 700;
        color: #F5C14A;
    }
    .cmp .sym { font-size: 1.2rem; font-weight: 800; color: #F4F7FB; margin: 0.15rem 0 0.2rem; }
    .cmp .side {
        display: inline-block;
        padding: 0.12rem 0.5rem;
        border-radius: 999px;
        font-size: 0.72rem;
        font-weight: 700;
    }
    .cmp .side.call { background: rgba(61,220,151,0.18); color: #3DDC97; }
    .cmp .side.put { background: rgba(255,107,122,0.18); color: #FF6B7A; }
    .cmp .strike { color: #C5D0E0; font-size: 0.86rem; margin-top: 0.25rem; font-weight: 600; }
    .cmp td { color: #F4F7FB; font-size: 0.95rem; font-weight: 600; }
    .cmp td .sub { display: block; font-size: 0.72rem; color: #94A3B8; font-weight: 500; margin-top: 0.1rem; }
    .cmp tr.group td, .cmp tr.group th { background: #0E1626; }
    .cmp td.best { color: #3DDC97; }
    .cmp td.buy { color: #3DDC97; }
    .cmp td.sell { color: #7DD3FC; }
    .cmp td.stop { color: #FF6B7A; }
    .cmp td.gold { color: #F5C14A; }
    .cmp tbody tr:last-child td { border-bottom: 0; }
    .cmp-note { color: #94A3B8; font-size: 0.82rem; margin: 0.15rem 0 0.6rem; }
    .cmp-shared {
        border: 1px solid #2A3550;
        background: #121A2C;
        border-radius: 14px;
        padding: 0.7rem 0.9rem 0.75rem;
        margin: 0 0 0.65rem;
    }
    .cmp-shared-kicker {
        font-size: 0.7rem;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        font-weight: 700;
        color: #94A3B8;
        margin-bottom: 0.4rem;
    }
    .cmp-shared .chip { font-size: 0.82rem; padding: 0.28rem 0.7rem; }
</style>
"""


def inject_css() -> None:
    st.markdown(APP_CSS, unsafe_allow_html=True)


def market_banner_html(ctx) -> str:
    return (
        f'<div class="mkt {escape(ctx.regime)}">'
        f'<div class="mkt-kicker">Market &amp; global · {escape(ctx.as_of)} · {escape(ctx.regime)}</div>'
        f"<h3>{escape(ctx.headline)}</h3>"
        f"<p>{escape(ctx.nifty)}</p>"
        f"<p>{escape(ctx.global_note)}</p>"
        f"<p>{escape(ctx.note)}</p>"
        f"</div>"
    )


def eligibility_label(value: str | Eligibility) -> str:
    key = value.value if isinstance(value, Eligibility) else value
    return ELIGIBILITY_LABELS.get(key, key)


def fmt_num(value: Optional[float], *, digits: int = 2, prefix: str = "", suffix: str = "") -> str:
    if value is None:
        return "—"
    return f"{prefix}{value:,.{digits}f}{suffix}"


def fmt_int(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{value:,.0f}"


def action_plain(action: Optional[str]) -> str:
    if not action or action == "NONE":
        return "No buy idea"
    return action.replace("_", " ")


def cover_chip_class(cover: Optional[float]) -> str:
    if cover is None:
        return ""
    if cover >= 1.5:
        return "ok"
    if cover >= 1.0:
        return "warn"
    return "bad"


def eligibility_chip_class(value: str) -> str:
    if value == Eligibility.NAKED_BUY_OK.value:
        return "ok"
    if value == Eligibility.SPREAD_ONLY.value:
        return "warn"
    if value == Eligibility.EXCLUDE.value:
        return "bad"
    return "info"


def style_eligibility(df: pd.DataFrame):
    if df.empty or "Readiness" not in df.columns:
        return df

    reverse = {v: k for k, v in ELIGIBILITY_LABELS.items()}

    def highlight(row):
        raw = reverse.get(row.get("Readiness", ""), "")
        color = ELIGIBILITY_COLORS.get(raw, "")
        return [f"background-color: {color}" if color else "" for _ in row]

    return df.style.apply(highlight, axis=1)


def priority_display_frame(ranked, *, top_n: int = 5, plans: dict | None = None) -> pd.DataFrame:
    plans = plans or {}
    records = []
    for item in ranked:
        row = item.row
        plan = plans.get(row.symbol)
        rec = {
            "#": item.rank,
            "Top 5": "★ Top 5" if item.rank <= top_n else "",
            "Priority": item.band,
            "Potential": item.potential,
            "Symbol": row.symbol,
            "Idea": action_plain(row.suggestion_action),
            "Strike": row.suggestion_strike,
            "CE/PE": row.suggestion_option_type,
            "Lot": row.lot_size,
            "IV Rank": None if row.iv_rank is None else round(row.iv_rank, 0),
            "Event": (
                None
                if row.event_days is None
                else f"{row.event_kind or 'EVT'} {row.event_days}d"
            ),
            "Spread %": None
            if row.bid_ask_pct is None
            else round(row.bid_ask_pct * 100, 2),
            "Buy": None if plan is None else round(plan.option_buy, 2),
            "Sell": None if plan is None else round(plan.option_sell, 2),
            "Stop": None if plan is None else round(plan.option_stop, 2),
            "Margin %": None if plan is None else round(plan.profit_margin_pct, 1),
            "R:R": None if plan is None else round(plan.reward_risk, 2),
            "Cover": None
            if row.suggestion_move_cover_ratio is None
            else round(row.suggestion_move_cover_ratio, 2),
            "Score": None if row.score is None else round(row.score, 1),
            "Why this rank": item.why,
        }
        records.append(rec)
    return pd.DataFrame.from_records(records)


def priority_column_config() -> dict[str, Any]:
    cfg = scanner_column_config()
    cfg.update(
        {
            "#": st.column_config.NumberColumn("#", help="1 = highest estimated profit potential."),
            "Top 5": st.column_config.TextColumn("Top 5", help="Highlighted shortlist to buy first."),
            "Priority": st.column_config.TextColumn(
                "Priority",
                help="High ≥70 · Medium ≥50 · Low <50 on the potential score.",
            ),
            "Potential": st.column_config.NumberColumn(
                "Potential",
                format="%.0f",
                min_value=0,
                max_value=100,
                help="0–100 rank of how realistically the suggested buy can reach profit.",
            ),
            "Premium": st.column_config.NumberColumn("Premium", format="₹%.2f"),
            "Lot": st.column_config.NumberColumn(
                "Lot",
                format="%d",
                help="NSE F&O board lot (shares per lot).",
            ),
            "IV Rank": st.column_config.NumberColumn(
                "IV Rank",
                format="%.0f",
                help="0–100 vs stored daily ATM IV. High = expensive vol.",
            ),
            "Event": st.column_config.TextColumn("Event", help="Days to earnings or corporate action."),
            "Spread %": st.column_config.NumberColumn(
                "Spread %",
                format="%.2f%%",
                help="Live ATM bid–ask when the chain is available.",
            ),
            "Buy": st.column_config.NumberColumn("Buy", format="₹%.2f", help="Enter the option near this last-close premium."),
            "Sell": st.column_config.NumberColumn("Sell", format="₹%.2f", help="First profit-book level (regime R multiple, capped by 1-ATR)."),
            "Stop": st.column_config.NumberColumn("Stop", format="₹%.2f", help="Exit the option if premium falls here."),
            "Margin %": st.column_config.NumberColumn("Margin %", format="%.1f%%", help="(Sell − Buy) ÷ Buy."),
            "R:R": st.column_config.NumberColumn("R:R", format="%.2f", help="Reward ÷ risk on the option premium."),
            "1-ATR P&L": st.column_config.NumberColumn(
                "1-ATR P&L",
                format="₹%.2f",
                help="Ideal to-expiry P&L per share if the stock moves 1 ATR in the idea's direction.",
            ),
            "Why this rank": st.column_config.TextColumn("Why this rank"),
        }
    )
    return cfg


def style_priority(df: pd.DataFrame):
    if df.empty:
        return df

    def highlight(row):
        if str(row.get("Top 5", "")).startswith("★"):
            color = "rgba(245, 193, 74, 0.22)"
        elif row.get("Priority") == "High":
            color = "rgba(61, 220, 151, 0.16)"
        else:
            color = ""
        return [f"background-color: {color}" if color else "" for _ in row]

    return df.style.apply(highlight, axis=1)


def scanner_display_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Friendly subset + labels for the main table."""
    if df.empty:
        return df
    out = df.copy()
    out["Readiness"] = out["Eligibility"].map(eligibility_label)
    out["Idea"] = out["Action"].map(action_plain)
    rename = {
        "Need%": "Need %",
        "Cover×": "Cover",
        "Spot": "Close",
        "ATR%": "ATR %",
        "Opt": "CE/PE",
        "Bias": "Bias",
    }
    out = out.rename(columns=rename)
    cols = [
        c
        for c in [
            "Symbol",
            "Idea",
            "Strike",
            "CE/PE",
            "Breakeven",
            "Need %",
            "Cover",
            "Close",
            "ATR %",
            "Score",
            "Readiness",
            "Bias",
            "Why",
        ]
        if c in out.columns
    ]
    return out[cols]


def scanner_column_config() -> dict[str, Any]:
    return {
        "#": st.column_config.NumberColumn(
            "#",
            help="Buy-idea rank. Blank = no BUY CALL/PUT suggestion.",
        ),
        "Symbol": st.column_config.TextColumn("Symbol", width="small"),
        "Idea": st.column_config.TextColumn("Idea", help="Buy call or buy put — never a short/write."),
        "Strike": st.column_config.NumberColumn("Strike", format="%.0f"),
        "CE/PE": st.column_config.TextColumn("CE/PE", help="CE = call, PE = put"),
        "Breakeven": st.column_config.NumberColumn(
            "Breakeven",
            format="%.2f",
            help="Call: strike + premium. Put: strike − premium. Expiry P&L is zero here.",
        ),
        "Need %": st.column_config.NumberColumn(
            "Need %",
            format="%.2f%%",
            help="How far the stock must move from last close to reach breakeven.",
        ),
        "Cover": st.column_config.NumberColumn(
            "Cover",
            format="%.2f×",
            help="Expected move (ATR × √hold days) ÷ required move. Above 1.5× is healthier.",
        ),
        "Close": st.column_config.NumberColumn("Close", format="%.2f"),
        "ATR %": st.column_config.NumberColumn(
            "ATR %",
            format="%.2f%%",
            help="Typical daily range as % of close. Higher = more room for option buyers.",
        ),
        "Score": st.column_config.NumberColumn(
            "Score",
            format="%.0f",
            min_value=0,
            max_value=100,
            help="0–100 composite from last-close technicals, liquidity, and move vs premium.",
        ),
        "Readiness": st.column_config.TextColumn("Readiness"),
        "Bias": st.column_config.TextColumn("Bias"),
        "Why": st.column_config.TextColumn("Why this name"),
    }


def top_priority_cards_html(ranked, *, limit: int = 5) -> str:
    if not ranked:
        return ""
    cards = []
    for item in ranked[:limit]:
        row = item.row
        band = item.band.lower()
        idea = action_plain(row.suggestion_action)
        strike = (
            f"{row.suggestion_strike:.0f} {row.suggestion_option_type}"
            if row.suggestion_strike is not None
            else ""
        )
        cover = (
            f"Cover {row.suggestion_move_cover_ratio:.2f}×"
            if row.suggestion_move_cover_ratio is not None
            else ""
        )
        cards.append(
            f'<div class="prio-card {escape(band)} top5">'
            f'<div class="prio-badge">TOP {item.rank}</div>'
            f'<div class="prio-rank">#{item.rank} · {escape(item.band)} potential</div>'
            f'<div class="prio-sym">{escape(row.symbol)}</div>'
            f'<div class="prio-meta">{escape(idea)} {escape(strike)}<br/>'
            f'{escape(cover)} · potential {item.potential:.0f}</div>'
            f"</div>"
        )
    return f'<div class="prio-grid">{"".join(cards)}</div>'


def _short_expiry(value: Any) -> str:
    if not value:
        return "—"
    text = str(value)
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").strftime("%d %b")
    except ValueError:
        return text


def _event_label(row: SymbolRow) -> str:
    days = getattr(row, "event_days", None)
    if days is None:
        return "—"
    kind = getattr(row, "event_kind", None) or "Event"
    return f"{kind} {int(days)}d"


def _best_index(values: list[Optional[float]], *, higher: bool = True) -> Optional[int]:
    ranked = [(i, v) for i, v in enumerate(values) if v is not None]
    if not ranked:
        return None
    return (max if higher else min)(ranked, key=lambda item: item[1])[0]


def _cmp_cell(text: str, *, css: str = "", sub: str = "", best: bool = False) -> str:
    klass = " ".join(part for part in (css, "best" if best else "") if part)
    extra = f'<span class="sub">{escape(sub)}</span>' if sub else ""
    attr = f' class="{klass}"' if klass else ""
    return f"<td{attr}>{escape(text)}{extra}</td>"


def _metric_row(
    label: str,
    values: list[str],
    *,
    subs: list[str] | None = None,
    css: list[str] | None = None,
    best: int | None = None,
    group: bool = False,
) -> dict[str, Any]:
    n = len(values)
    return {
        "label": label,
        "values": values,
        "subs": subs or [""] * n,
        "css": css or [""] * n,
        "best": best,
        "group": group,
    }


def _is_shared_metric(metric: dict[str, Any], *, n_cols: int) -> bool:
    if n_cols < 2:
        return False
    keys = [f"{v}|{s}" for v, s in zip(metric["values"], metric["subs"])]
    if len(set(keys)) != 1:
        return False
    return metric["values"][0] not in {"", "—"}


def _shared_strip_html(metrics: list[dict[str, Any]]) -> str:
    if not metrics:
        return ""
    chips = []
    for metric in metrics:
        text = metric["values"][0]
        sub = metric["subs"][0]
        label = f"{metric['label']} {text}"
        if sub:
            label = f"{label} · {sub}"
        chips.append(f'<span class="chip info">{escape(label)}</span>')
    return (
        '<div class="cmp-shared">'
        f'<div class="chip-row">{"".join(chips)}</div>'
        "</div>"
    )


def compare_top5_html(ranked, plans: dict | None = None, *, limit: int = 5) -> str:
    """Side-by-side Top 5 board so a trader can pick one contract."""
    plans = plans or {}
    items = list(ranked[:limit])
    if not items:
        return ""

    covers = [getattr(item.row, "suggestion_move_cover_ratio", None) for item in items]
    margins = [
        None if plans.get(item.row.symbol) is None else plans[item.row.symbol].profit_margin_pct
        for item in items
    ]
    costs = []
    for item in items:
        row = item.row
        cost = row.suggestion_premium_per_lot
        if cost is None and row.lot_size and row.suggestion_premium:
            cost = float(row.lot_size) * float(row.suggestion_premium)
        costs.append(cost)
    profits = [
        None if plans.get(item.row.symbol) is None else plans[item.row.symbol].profit_per_lot
        for item in items
    ]
    best_cover = _best_index(covers, higher=True)
    best_margin = _best_index(margins, higher=True)
    best_cost = _best_index(costs, higher=False)
    best_profit = _best_index(profits, higher=True)

    heads = ['<th class="metric">Compare</th>']
    for i, item in enumerate(items):
        row = item.row
        action = getattr(row, "suggestion_action", None) or "NONE"
        side = "call" if action == "BUY_CALL" else "put" if action == "BUY_PUT" else ""
        pick = " pick" if i == 0 else ""
        strike = (
            f"{row.suggestion_strike:.0f} {row.suggestion_option_type or ''}"
            if row.suggestion_strike is not None
            else "—"
        )
        label = row.suggestion_label or ""
        heads.append(
            f'<th class="col {side}{pick}">'
            f'<div class="rank">#{item.rank} · {escape(item.band)}</div>'
            f'<div class="sym">{escape(row.symbol)}</div>'
            f'<div class="side {side}">{escape(action_plain(action))}</div>'
            f'<div class="strike">{escape(strike)} · {escape(label)}</div>'
            f"</th>"
        )

    def col(fn) -> list:
        return [fn(item) for item in items]

    def plan_of(item):
        return plans.get(item.row.symbol)

    metrics = [
        _metric_row(
            "Session",
            col(lambda it: it.row.as_of_date or "—"),
            group=True,
        ),
        _metric_row(
            "Expiry",
            col(lambda it: _short_expiry(it.row.expiry)),
            subs=col(lambda it: f"{it.row.dte}d left" if it.row.dte is not None else ""),
            group=True,
        ),
        _metric_row(
            "Premium",
            col(lambda it: fmt_num(it.row.suggestion_premium, prefix="₹")),
            css=["gold"] * len(items),
        ),
        _metric_row(
            "Lot",
            col(lambda it: f"{int(it.row.lot_size):,}" if it.row.lot_size else "—"),
            subs=["shares / lot"] * len(items),
        ),
        _metric_row(
            "Cost / lot",
            [fmt_num(c, digits=0, prefix="₹") for c in costs],
            subs=["debit / lot"] * len(items),
            css=["gold"] * len(items),
            best=best_cost,
        ),
        _metric_row(
            "Buy",
            col(lambda it: fmt_num(plan_of(it).option_buy, prefix="₹") if plan_of(it) else "—"),
            css=["buy"] * len(items),
            group=True,
        ),
        _metric_row(
            "Sell / book",
            col(lambda it: fmt_num(plan_of(it).option_sell, prefix="₹") if plan_of(it) else "—"),
            css=["sell"] * len(items),
        ),
        _metric_row(
            "Stop",
            col(lambda it: fmt_num(plan_of(it).option_stop, prefix="₹") if plan_of(it) else "—"),
            css=["stop"] * len(items),
        ),
        _metric_row(
            "Margin",
            col(
                lambda it: fmt_num(plan_of(it).profit_margin_pct, suffix="%")
                if plan_of(it)
                else "—"
            ),
            css=["gold"] * len(items),
            best=best_margin,
        ),
        _metric_row(
            "R : R",
            col(lambda it: fmt_num(plan_of(it).reward_risk, digits=2) if plan_of(it) else "—"),
            subs=col(lambda it: plan_of(it).regime if plan_of(it) else ""),
        ),
        _metric_row(
            "Profit / lot",
            col(
                lambda it: fmt_num(plan_of(it).profit_per_lot, digits=0, prefix="₹")
                if plan_of(it)
                else "—"
            ),
            css=["buy"] * len(items),
            best=best_profit,
        ),
        _metric_row(
            "Risk / lot",
            col(
                lambda it: fmt_num(plan_of(it).risk_per_lot, digits=0, prefix="₹")
                if plan_of(it)
                else "—"
            ),
            css=["stop"] * len(items),
        ),
        _metric_row(
            "Breakeven",
            col(lambda it: fmt_num(it.row.suggestion_breakeven)),
            group=True,
        ),
        _metric_row(
            "Need",
            col(lambda it: fmt_num(it.row.suggestion_required_move_pct, suffix="%")),
        ),
        _metric_row(
            "Cover",
            col(lambda it: fmt_num(it.row.suggestion_move_cover_ratio, suffix="×")),
            css=[cover_chip_class(c) for c in covers],
            best=best_cover,
        ),
        _metric_row(
            "IV Rank",
            col(lambda it: fmt_num(getattr(it.row, "iv_rank", None), digits=0)),
        ),
        _metric_row(
            "Event",
            col(lambda it: _event_label(it.row)),
        ),
        _metric_row(
            "Why this rank",
            col(lambda it: (it.why or "")[:72] or "—"),
        ),
    ]

    shared = [m for m in metrics if _is_shared_metric(m, n_cols=len(items))]
    shared_ids = {id(m) for m in shared}
    unique = [m for m in metrics if id(m) not in shared_ids]

    def row_html(metric: dict[str, Any]) -> str:
        klass = ' class="group"' if metric["group"] else ""
        cells = [
            _cmp_cell(
                value,
                css=css,
                sub=sub,
                best=metric["best"] is not None and i == metric["best"],
            )
            for i, (value, sub, css) in enumerate(
                zip(metric["values"], metric["subs"], metric["css"])
            )
        ]
        return (
            f"<tr{klass}><th class=\"metric\">{escape(metric['label'])}</th>"
            f"{''.join(cells)}</tr>"
        )

    body = "".join(row_html(metric) for metric in unique)
    return (
        '<div class="cmp-wrap">'
        f"{_shared_strip_html(shared)}"
        '<table class="cmp">'
        f"<thead><tr>{''.join(heads)}</tr></thead>"
        f"<tbody>{body}</tbody>"
        "</table></div>"
    )


def idea_card_html(row: SymbolRow) -> str:
    action = getattr(row, "suggestion_action", None) or "NONE"
    if action == "BUY_CALL":
        kind = "call"
        kicker = "Suggested buy · Call"
    elif action == "BUY_PUT":
        kind = "put"
        kicker = "Suggested buy · Put"
    else:
        kind = "none"
        kicker = "No buy idea"

    title = escape(getattr(row, "suggestion_summary", None) or action_plain(action))
    rationale = escape(getattr(row, "suggestion_rationale", None) or row.why or "")
    elig = row.eligibility.value
    chips = [
        f'<span class="chip {eligibility_chip_class(elig)}">{escape(eligibility_label(elig))}</span>',
        f'<span class="chip">{escape(row.direction_bias.value)} bias</span>',
    ]
    if row.expiry:
        chips.append(f'<span class="chip">Expiry {escape(str(row.expiry))}</span>')
    if row.dte is not None:
        chips.append(f'<span class="chip">{int(row.dte)} days left</span>')
    if row.lot_size:
        chips.append(f'<span class="chip violet">Lot {int(row.lot_size):,}</span>')
    cover = getattr(row, "suggestion_move_cover_ratio", None)
    if cover is not None:
        chips.append(
            f'<span class="chip {cover_chip_class(cover)}">Cover {cover:.2f}×</span>'
        )
    return (
        f'<div class="idea-card {kind}">'
        f'<div class="idea-kicker">{kicker}</div>'
        f'<div class="idea-title">{title}</div>'
        f'<div class="idea-sub">{rationale}</div>'
        f'<div class="chip-row">{"".join(chips)}</div>'
        f"</div>"
    )


def _tile(kind: str, label: str, value: str, sub: str = "") -> str:
    extra = f'<div class="sub">{escape(sub)}</div>' if sub else ""
    return (
        f'<div class="tile {escape(kind)}">'
        f'<div class="lbl">{escape(label)}</div>'
        f'<div class="val">{escape(value)}</div>'
        f"{extra}</div>"
    )


def trade_idea_panel_html(row: SymbolRow, plan=None) -> str:
    """Colorful Trade idea tiles, including NSE lot size."""
    action = getattr(row, "suggestion_action", None) or "NONE"
    side = "call" if action == "BUY_CALL" else "put" if action == "BUY_PUT" else ""
    strike = (
        f"{row.suggestion_strike:.0f} {row.suggestion_option_type}"
        if row.suggestion_strike is not None
        else "—"
    )
    lot = row.lot_size
    lot_txt = f"{int(lot):,}" if lot else "—"
    cost = row.suggestion_premium_per_lot
    if cost is None and lot and row.suggestion_premium:
        cost = float(lot) * float(row.suggestion_premium)

    contract = [
        _tile(side or "", "Action", action_plain(action), row.suggestion_label or ""),
        _tile("violet", "Strike", strike, row.expiry or ""),
        _tile(
            "gold",
            "Premium",
            fmt_num(row.suggestion_premium, prefix="₹"),
            f"EOD last traded · {row.as_of_date or 'session'}",
        ),
        _tile("violet", "Lot size", lot_txt, "shares / lot (NSE)"),
        _tile("gold", "Cost / lot", fmt_num(cost, digits=0, prefix="₹"), f"{lot_txt} × premium"),
        _tile("", "Max lots", fmt_int(row.suggestion_max_lots), "IN10 budget"),
    ]

    levels = []
    if plan is not None:
        levels = [
            _tile("buy", "Buy", fmt_num(plan.option_buy, prefix="₹"), "enter near last close"),
            _tile("sell", "Sell / book", fmt_num(plan.option_sell, prefix="₹"), "first target"),
            _tile("stop", "Stop loss", fmt_num(plan.option_stop, prefix="₹"), "exit if hit"),
            _tile("gold", "Profit margin", fmt_num(plan.profit_margin_pct, suffix="%"), "on premium"),
            _tile("violet", "R : R", fmt_num(plan.reward_risk, digits=2), plan.regime),
        ]
        money = [
            _tile("buy", "Profit / lot", fmt_num(plan.profit_per_lot, digits=0, prefix="₹"), f"lot {lot_txt}"),
            _tile("stop", "Risk / lot", fmt_num(plan.risk_per_lot, digits=0, prefix="₹"), f"lot {lot_txt}"),
            _tile("stop", "Stock stop", fmt_num(plan.stock_stop), "underlying"),
            _tile("sell", "Stock target", fmt_num(plan.stock_target), "underlying"),
        ]
    else:
        money = []

    be = getattr(row, "suggestion_breakeven", None)
    hurdle = [
        _tile("gold", "Breakeven", fmt_num(be), "strike ± premium"),
        _tile("", "Need (pts)", fmt_num(row.suggestion_required_move_pts, digits=1)),
        _tile("", "Need (%)", fmt_num(row.suggestion_required_move_pct, suffix="%")),
        _tile("violet", "Expected move", fmt_num(row.suggestion_expected_move_pts, digits=1), "ATR × √days"),
        _tile(
            cover_chip_class(row.suggestion_move_cover_ratio) or "gold",
            "Cover",
            fmt_num(row.suggestion_move_cover_ratio, suffix="×"),
            "expected ÷ need",
        ),
    ]

    parts = [
        '<div class="idea-panel">',
        '<div class="idea-row-title">Contract</div>',
        f'<div class="tile-grid">{"".join(contract)}</div>',
    ]
    if levels:
        parts += [
            '<div class="idea-row-title">Buy · sell · stop</div>',
            f'<div class="tile-grid five">{"".join(levels)}</div>',
            '<div class="idea-row-title">Money per lot</div>',
            f'<div class="tile-grid four">{"".join(money)}</div>',
        ]
    parts += [
        '<div class="idea-row-title">Can the stock reach breakeven?</div>',
        f'<div class="tile-grid five">{"".join(hurdle)}</div>',
        "</div>",
    ]
    return "".join(parts)


def friendly_checklist(items: list[dict[str, str]]) -> pd.DataFrame:
    rows = []
    for item in items:
        rid = item.get("rule_id", "")
        rows.append(
            {
                "Check": RULE_LABELS.get(rid, rid),
                "Code": rid,
                "Result": item.get("status", ""),
                "Detail": item.get("detail", ""),
            }
        )
    return pd.DataFrame(rows)


def friendly_scenarios(scenarios: list[dict[str, Any]]) -> pd.DataFrame:
    labels = {
        "spot": "If stock stays at last close",
        "+1 ATR": "If stock rises by 1 ATR",
        "-1 ATR": "If stock falls by 1 ATR",
        "breakeven": "At breakeven (zero P&L)",
    }
    rows = []
    for s in scenarios:
        key = s.get("scenario", "")
        rows.append(
            {
                "What if": labels.get(key, key),
                "Stock at": s.get("spot"),
                "P&L / share (₹)": s.get("pnl_per_share"),
            }
        )
    return pd.DataFrame(rows)
