from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import streamlit as st

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.features.backtest import (
    STRICT_DESK,
    WIDE_DESK,
    BacktestService,
    passes_strict_desk,
)
from app.features.market_context import get_market_context
from app.features.priority import high_priority_ideas, top_buys
from app.features.trade_plan import build_trade_plan
from app.models.schemas import InstrumentType
from app.runtime import app_version, build_scanner
from app.scanner import ScannerService
from app.scoring.checklist import build_checklist
from app.ui import (
    ELIGIBILITY_HELP,
    compare_top5_html,
    eligibility_label,
    fmt_int,
    fmt_num,
    friendly_checklist,
    friendly_scenarios,
    idea_card_html,
    inject_css,
    market_banner_html,
    priority_column_config,
    priority_display_frame,
    style_priority,
    trade_idea_panel_html,
)

st.set_page_config(
    page_title="Option Buying Desk",
    page_icon="📈",
    layout="wide",
)

TOP_N = 5


@dataclass(frozen=True)
class _ScanControls:
    use_subset: bool
    force_refresh: bool
    bt_mode: str
    bt_sessions: int
    run_backtest: bool


def _stock_symbols(scanner: ScannerService, *, use_subset: bool):
    return [
        m
        for m in scanner.load_symbols(use_subset=use_subset)
        if m.instrument_type == InstrumentType.STOCK
    ]


def _row_as_of(row) -> str | None:
    return row.as_of_date


def _render_backtest(report) -> None:
    st.markdown(
        '<div class="section-title">Backtest — did the last-close picks work?</div>',
        unsafe_allow_html=True,
    )
    scored = report.scored
    c1, c2, c3, c4, c5 = st.columns(5)
    st.caption(f"Mode: **{getattr(report, 'mode', 'wide')}** — judge Avg P&L, not win rate alone.")
    c1.metric("Signals", f"{len(report.signal_dates)}")
    c2.metric("Trades scored", f"{len(scored)}")
    c3.metric(
        "Win rate",
        "—" if report.win_rate is None else f"{report.win_rate:.0f}%",
    )
    c4.metric(
        "Avg P&L",
        "—" if report.avg_pnl_pct is None else f"{report.avg_pnl_pct:.1f}%",
    )
    c5.metric(
        "Target / stop",
        "—"
        if report.target_rate is None
        else f"{report.target_rate:.0f}% / {report.stop_rate:.0f}%",
    )
    for note in report.notes:
        st.caption(note)
    split = report.split_frame()
    if not split.empty:
        st.markdown("**Where the edge is**")
        st.dataframe(split, width="stretch", hide_index=True)
    frame = report.to_frame()
    if not frame.empty:
        st.dataframe(frame, width="stretch", hide_index=True, height=min(360, 64 + 36 * max(len(frame), 3)))
        st.download_button(
            "Download backtest (CSV)",
            data=frame.to_csv(index=False).encode("utf-8"),
            file_name="option_desk_backtest.csv",
            mime="text/csv",
        )


def _render_hero(as_of: str | None, *, universe_label: str) -> None:
    as_of_txt = f"Last F&amp;O close · {as_of}" if as_of else "Last market close · not live ticks"
    st.markdown(
        f"""
        <div class="hero">
          <div class="hero-kicker">NSE F&amp;O · stock options only</div>
          <h1>Option Buying Desk</h1>
          <p>
            High-priority <b>buy</b> calls and puts only. {universe_label}.
            {as_of_txt}. Not investment advice.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_sidebar() -> _ScanControls:
    with st.sidebar:
        st.markdown("### Scan")
        use_subset = st.toggle(
            "Fast scan (liquid 20)",
            value=True,
            help="On: score the liquid 20. Off: score the full F&O stock list, then keep High only.",
        )
        force_refresh = st.toggle("Reload EOD files", value=False)
        st.caption("Stocks only. The page lists High-priority buys — not the full scanner.")

        with st.expander("What the words mean"):
            st.markdown(
                """
                **High priority** — strongest last-close chance the option can
                reach profit (cover, 1-ATR P&L, readiness, ATR%, strike).

                **Top 5** — the first five High names to consider buying.

                **Breakeven (BE)** — Call = strike + premium. Put = strike − premium.

                **Cover** — expected move ÷ need. Above **1.5×** is healthier.

                **ATR** — typical daily range of the stock.

                **Buy / Sell / Stop** — option premium levels from last close,
                sized to the current market regime (tighter stops when India is
                cautious vs Wall Street).
                **Margin %** — (Sell − Buy) ÷ Buy. **R:R** — reward ÷ risk.
                """
            )

        st.markdown("### Backtest")
        bt_mode = st.radio(
            "Desk mode",
            options=["strict", "wide"],
            index=0,
            help="Strict: Top 2, cover ≥ 1.5×, close-only stop, 4-day hold. "
            "Wide: the old Top 5 / 2-day / day’s-low stop run.",
        )
        bt_sessions = st.slider(
            "Past signal sessions",
            min_value=5,
            max_value=20,
            value=15,
            help="How many prior closes to replay. Needs that many + hold days of bhav files.",
        )
        run_backtest = st.button("Replay past sessions")
        st.caption(f"Build {app_version()}")
    return _ScanControls(
        use_subset=use_subset,
        force_refresh=force_refresh,
        bt_mode=bt_mode,
        bt_sessions=bt_sessions,
        run_backtest=run_backtest,
    )


def _ensure_session() -> None:
    if "scan_rows" not in st.session_state:
        st.session_state.scan_rows = []
    if "backtest" not in st.session_state:
        st.session_state.backtest = None


def _run_scan(scanner: ScannerService, controls: _ScanControls) -> None:
    metas = _stock_symbols(scanner, use_subset=controls.use_subset)
    with st.spinner(f"Scoring {len(metas)} stocks from last close…"):
        st.session_state.scan_rows = scanner.scan_many(
            metas, force_refresh=controls.force_refresh
        )
    st.rerun()


def _run_backtest(scanner: ScannerService, controls: _ScanControls) -> None:
    metas = _stock_symbols(scanner, use_subset=controls.use_subset)
    with st.spinner(
        f"Replaying {controls.bt_sessions} sessions on {len(metas)} names "
        "(downloads extra bhav files)…"
    ):
        settings = STRICT_DESK if controls.bt_mode == "strict" else WIDE_DESK
        st.session_state.backtest = BacktestService(scanner).run(
            metas,
            signal_sessions=controls.bt_sessions,
            settings=settings,
        )


def _render_ideas(rows, high, top5, plans) -> bool:
    """Return False when there are no High ideas to show."""
    st.markdown(market_banner_html(get_market_context()), unsafe_allow_html=True)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Scanned", f"{len(rows)}")
    k2.metric("High priority", f"{len(high)}")
    k3.metric("Top 5", f"{len(top5)}")
    k4.metric("Top pick", top5[0].row.symbol if top5 else "—")

    st.markdown(
        '<div class="section-title">Trade ideas — compare Top 5</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="cmp-note">Same last-close session for every column. '
        "Green = desk pick / best in that row. Scan across, then pick one to trade. "
        "Not live quotes.</p>",
        unsafe_allow_html=True,
    )
    if not top5:
        st.warning(
            "No High-priority buy ideas in this scan. "
            "Turn off **Fast scan** and refresh to score the full F&O list."
        )
        return False

    st.markdown(
        compare_top5_html(top5, plans, limit=TOP_N),
        unsafe_allow_html=True,
    )
    strict_names = [
        item.row.symbol
        for item in top5
        if passes_strict_desk(item.row, STRICT_DESK)
    ][:2]
    if strict_names:
        st.info(
            "Strict desk (what to actually buy): **"
            + ", ".join(strict_names)
            + "** — cover ≥ 1.5×, ATM/ITM, IV Rank < 50, no near event."
        )
    else:
        st.warning(
            "Strict desk: none of the Top 5 pass. Skip the session — do not force five tickets."
        )

    st.markdown(
        '<div class="section-title">High-priority buy options</div>',
        unsafe_allow_html=True,
    )
    st.caption("Only High-potential BUY CALL / BUY PUT names. Top 5 rows are highlighted.")
    high_df = priority_display_frame(high, top_n=TOP_N, plans=plans)
    st.dataframe(
        style_priority(high_df),
        width="stretch",
        hide_index=True,
        column_config=priority_column_config(),
        height=min(420, 64 + 36 * max(len(high), 3)),
    )
    st.download_button(
        "Download High-priority list (CSV)",
        data=high_df.to_csv(index=False).encode("utf-8"),
        file_name="high_priority_buys.csv",
        mime="text/csv",
    )
    return True


def _render_detail(high, plans) -> None:
    st.markdown('<div class="section-title">Look closer</div>', unsafe_allow_html=True)
    symbols = [item.row.symbol for item in high]
    selected = st.selectbox(
        "Open one name for Why / nearby strikes / chain",
        options=symbols,
        help="Top 5 are already compared above. Use this for extra detail.",
    )
    detail = next(item.row for item in high if item.row.symbol == selected)
    st.markdown(idea_card_html(detail), unsafe_allow_html=True)

    tab_plan, tab_why, tab_chain = st.tabs(
        ["This name’s plan", "Why this stock", "Option chain"]
    )

    with tab_plan:
        if detail.has_buy_idea():
            plan = plans.get(detail.symbol)
            st.markdown(trade_idea_panel_html(detail, plan), unsafe_allow_html=True)
            if plan is not None:
                st.caption(
                    f"{plan.regime} tape · {plan.note} "
                    "Levels are research marks from last close, not live quotes or advice."
                )
            st.caption(
                "Lot size is the NSE F&O board lot. Cost / lot = lot × premium. "
                "Call BE = strike + premium · Put BE = strike − premium."
            )

            scenarios = detail.suggestion_pnl_scenarios or []
            alts = detail.suggestion_alternates or []
            left, right = st.columns(2)
            with left:
                if scenarios:
                    st.markdown("**If held to expiry**")
                    st.dataframe(
                        friendly_scenarios(scenarios),
                        width="stretch",
                        hide_index=True,
                    )
            with right:
                if alts:
                    st.markdown("**Other nearby strikes**")
                    alt_df = pd.DataFrame(alts)
                    keep = [
                        c
                        for c in [
                            "label",
                            "strike",
                            "option_type",
                            "premium",
                            "breakeven",
                            "required_move_pct",
                            "rank_score",
                        ]
                        if c in alt_df.columns
                    ]
                    pretty = {
                        "label": "Which",
                        "strike": "Strike",
                        "option_type": "CE/PE",
                        "premium": "Premium",
                        "breakeven": "Breakeven",
                        "required_move_pct": "Need %",
                        "rank_score": "Rank",
                    }
                    st.dataframe(
                        alt_df[keep].rename(columns=pretty),
                        width="stretch",
                        hide_index=True,
                    )
        else:
            st.warning(
                detail.suggestion_rationale
                or "No BUY CALL / BUY PUT idea for this symbol."
            )

    with tab_why:
        elig = detail.eligibility.value
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("Last close", fmt_num(detail.spot))
        m2.metric("Score", fmt_num(detail.score, digits=1))
        m3.metric("ATM IV (est.)", fmt_num(detail.atm_iv, digits=1))
        m4.metric("OI near ATM", fmt_int(detail.oi_atm))
        m5.metric("Volume near ATM", fmt_int(detail.volume_atm))
        m6.metric("Move / premium", fmt_num(detail.move_vs_premium_ratio))
        e1, e2, e3, e4 = st.columns(4)
        e1.metric("IV Rank", fmt_num(detail.iv_rank, digits=0))
        e2.metric("IV Percentile", fmt_num(detail.iv_percentile, digits=0))
        e3.metric(
            "Next event",
            detail.event_kind or "—",
            None if detail.event_days is None else f"in {detail.event_days}d",
        )
        e4.metric(
            "Bid–ask",
            "—" if detail.bid_ask_pct is None else f"{detail.bid_ask_pct * 100:.2f}%",
        )
        if detail.in_fno_ban:
            st.error("IN1: this name is on the F&O ban list.")

        st.markdown(
            f"**Readiness:** {eligibility_label(elig)} — {ELIGIBILITY_HELP.get(elig, '')}"
        )
        st.markdown(f"**Why:** {detail.why}")
        if detail.warnings:
            st.warning(" · ".join(str(w) for w in detail.warnings))
        if detail.failed_rules:
            st.error("Failed checks: " + ", ".join(detail.failed_rules))
        else:
            st.caption("No failed hard-rule codes on this name.")

        st.markdown("**Rule checklist**")
        st.dataframe(
            friendly_checklist(build_checklist(detail)),
            width="stretch",
            hide_index=True,
        )

    with tab_chain:
        st.caption("ATM-window strikes from the last F&O bhavcopy close — not live quotes.")
        if detail.chain_rows:
            st.dataframe(pd.DataFrame(detail.chain_rows), width="stretch", hide_index=True)
        else:
            st.info("No EOD option rows for this symbol.")


def main() -> None:
    inject_css()
    scanner = build_scanner()
    controls = _render_sidebar()
    _ensure_session()

    universe_label = (
        "Universe: liquid 20 (fast scan)"
        if controls.use_subset
        else "Universe: full F&O stock list"
    )
    rows = st.session_state.scan_rows
    as_of = next((_row_as_of(r) for r in rows if _row_as_of(r)), None)
    _render_hero(as_of, universe_label=universe_label)

    if st.button("Refresh scan", type="primary"):
        _run_scan(build_scanner(), controls)

    if controls.run_backtest:
        _run_backtest(scanner, controls)

    if st.session_state.backtest is not None:
        _render_backtest(st.session_state.backtest)

    if not rows:
        st.info(
            "Click **Refresh scan**. Fast scan scores 20 liquid names; "
            "turn it off to score the full F&O list. Only High-priority buys are shown. "
            "Or run **Replay past sessions** in the sidebar to check recent hit rate."
        )
        return

    high = high_priority_ideas(rows)
    top5 = top_buys(high, limit=TOP_N)
    market = get_market_context()
    plans = {
        item.row.symbol: plan
        for item in high
        if (plan := build_trade_plan(item.row, market)) is not None
    }
    if not _render_ideas(rows, high, top5, plans):
        return
    _render_detail(high, plans)


if __name__ == "__main__":
    main()
