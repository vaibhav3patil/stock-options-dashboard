"""Replay last-close selection on past sessions and score option outcomes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from app.config import RulesConfig, get_rules
from app.data.providers.nse_bhavcopy import filter_fo_options
from app.features.priority import BuyPriority, high_priority_ideas, rerank, top_buys
from app.features.trade_plan import build_trade_plan
from app.models.schemas import SymbolMeta, SymbolRow
from app.scanner import ScannerService


@dataclass
class SessionQuote:
    date: str
    last: float
    high: float
    low: float
    close: float


@dataclass
class BacktestSettings:
    """wide = original desk replay. strict = fewer tickets, looser time, close stop."""

    mode: str = "strict"
    top_n: int = 2
    hold_sessions: int = 4
    stop_on: str = "close"  # low | close
    min_cover: Optional[float] = 1.5
    allow_otm: bool = False
    max_iv_rank: Optional[float] = 50
    skip_event_days: Optional[int] = 2


WIDE_DESK = BacktestSettings(
    mode="wide",
    top_n=5,
    hold_sessions=2,
    stop_on="low",
    min_cover=None,
    allow_otm=True,
    max_iv_rank=None,
    skip_event_days=None,
)
STRICT_DESK = BacktestSettings()


def passes_strict_desk(row: SymbolRow, settings: BacktestSettings | None = None) -> bool:
    """Same gates a buyer should use on the live Top 5 board."""
    settings = settings or STRICT_DESK
    cover = row.suggestion_move_cover_ratio
    if settings.min_cover is not None and (cover is None or cover < settings.min_cover):
        return False
    if not settings.allow_otm and row.suggestion_label == "OTM-1":
        return False
    ivr = row.iv_rank
    if settings.max_iv_rank is not None and ivr is not None and ivr >= settings.max_iv_rank:
        return False
    days = row.event_days
    if (
        settings.skip_event_days is not None
        and days is not None
        and days <= settings.skip_event_days
    ):
        return False
    return True


@dataclass
class BacktestTrade:
    signal_date: str
    exit_date: str
    symbol: str
    action: str
    strike: float
    option_type: str
    expiry: str
    entry: float
    exit_px: float
    stop: float
    target: float
    outcome: str  # TARGET | STOP | TIME | MISSING
    pnl_pct: Optional[float]
    pnl_per_lot: Optional[float]
    rank: int
    potential: float
    cover: Optional[float] = None
    label: Optional[str] = None


@dataclass
class BacktestReport:
    signal_dates: list[str]
    hold_sessions: int
    mode: str = "strict"
    trades: list[BacktestTrade] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def scored(self) -> list[BacktestTrade]:
        return [t for t in self.trades if t.outcome != "MISSING" and t.pnl_pct is not None]

    @property
    def wins(self) -> list[BacktestTrade]:
        return [t for t in self.scored if t.pnl_pct is not None and t.pnl_pct > 0]

    @property
    def win_rate(self) -> Optional[float]:
        if not self.scored:
            return None
        return 100.0 * len(self.wins) / len(self.scored)

    @property
    def avg_pnl_pct(self) -> Optional[float]:
        if not self.scored:
            return None
        return sum(t.pnl_pct or 0.0 for t in self.scored) / len(self.scored)

    @property
    def target_rate(self) -> Optional[float]:
        if not self.scored:
            return None
        return 100.0 * sum(1 for t in self.scored if t.outcome == "TARGET") / len(self.scored)

    @property
    def stop_rate(self) -> Optional[float]:
        if not self.scored:
            return None
        return 100.0 * sum(1 for t in self.scored if t.outcome == "STOP") / len(self.scored)

    def to_frame(self) -> pd.DataFrame:
        rows = []
        for t in self.trades:
            rows.append(
                {
                    "Signal": t.signal_date,
                    "Exit": t.exit_date,
                    "Symbol": t.symbol,
                    "Idea": t.action.replace("_", " "),
                    "Strike": t.strike,
                    "CE/PE": t.option_type,
                    "Rank": t.rank,
                    "Entry": round(t.entry, 2),
                    "Exit px": None if t.exit_px is None else round(t.exit_px, 2),
                    "Outcome": t.outcome,
                    "P&L %": None if t.pnl_pct is None else round(t.pnl_pct, 1),
                    "P&L / lot": None if t.pnl_per_lot is None else round(t.pnl_per_lot, 0),
                    "Cover": None if t.cover is None else round(t.cover, 2),
                    "Strike type": t.label or "",
                }
            )
        return pd.DataFrame.from_records(rows)

    def split_frame(self) -> pd.DataFrame:
        """Rank / cover buckets so we can see where the edge is."""
        scored = self.scored
        if not scored:
            return pd.DataFrame()

        def pack(name: str, items: list[BacktestTrade]) -> dict:
            if not items:
                return {"Bucket": name, "N": 0, "Win %": None, "Avg P&L %": None}
            wins = sum(1 for t in items if (t.pnl_pct or 0) > 0)
            avg = sum(t.pnl_pct or 0.0 for t in items) / len(items)
            return {
                "Bucket": name,
                "N": len(items),
                "Win %": round(100.0 * wins / len(items), 1),
                "Avg P&L %": round(avg, 1),
            }

        rows = [
            pack("All scored", scored),
            pack("Rank 1–2", [t for t in scored if t.rank <= 2]),
            pack("Rank 3–5", [t for t in scored if t.rank >= 3]),
            pack(
                f"Cover ≥ {STRICT_DESK.min_cover}×",
                [
                    t
                    for t in scored
                    if t.cover is not None
                    and STRICT_DESK.min_cover is not None
                    and t.cover >= STRICT_DESK.min_cover
                ],
            ),
            pack(
                f"Cover < {STRICT_DESK.min_cover}×",
                [
                    t
                    for t in scored
                    if t.cover is None
                    or STRICT_DESK.min_cover is None
                    or t.cover < STRICT_DESK.min_cover
                ],
            ),
        ]
        return pd.DataFrame.from_records(rows)


def lookup_option_quote(
    bhav: pd.DataFrame,
    *,
    symbol: str,
    strike: float,
    option_type: str,
    expiry: str,
) -> Optional[SessionQuote]:
    df = filter_fo_options(
        bhav,
        symbol,
        option_type=option_type,
        strike=strike,
        expiry=expiry,
    )
    if df.empty:
        return None
    row = df.iloc[0]
    last = float(row.get("LastPric") or 0) or float(row.get("ClsPric") or 0)
    close = float(row.get("ClsPric") or last)
    high = float(row.get("HghPric") or max(last, close))
    low = float(row.get("LwPric") or min(last, close))
    if last <= 0:
        return None
    trade_date = ""
    if "_trade_date" in row.index and pd.notna(row["_trade_date"]):
        trade_date = str(row["_trade_date"])
    elif "TradDt" in row.index and pd.notna(row["TradDt"]):
        trade_date = str(pd.to_datetime(row["TradDt"]).date())
    return SessionQuote(date=trade_date, last=last, high=high, low=low, close=close)


def simulate_hold(
    *,
    entry: float,
    stop: float,
    target: float,
    path: list[SessionQuote],
    stop_on: str = "low",
) -> tuple[str, float, str]:
    """
    Walk later sessions.
    stop_on=low: day's low tags stop (harsh). Same-day stop before target.
    stop_on=close: only a closing print below stop exits (how a desk should manage).
    """
    if not path:
        return "MISSING", entry, ""
    for quote in path:
        if stop_on == "close":
            if quote.close <= stop:
                return "STOP", quote.close, quote.date
            if quote.high >= target:
                return "TARGET", target, quote.date
        else:
            if quote.low <= stop:
                return "STOP", stop, quote.date
            if quote.high >= target:
                return "TARGET", target, quote.date
    last = path[-1]
    return "TIME", last.last or last.close, last.date


def _lot_qty(row: SymbolRow) -> Optional[float]:
    prem = getattr(row, "suggestion_premium", None)
    cost = getattr(row, "suggestion_premium_per_lot", None)
    if prem and prem > 0 and cost:
        return float(cost) / float(prem)
    if row.lot_size:
        return float(row.lot_size)
    return None


def close_trade(
    row: SymbolRow,
    *,
    signal_date: str,
    path: list[SessionQuote],
    rank: int,
    potential: float,
    stop_on: str = "low",
) -> BacktestTrade:
    plan = build_trade_plan(row)
    entry = float(row.suggestion_premium or 0)
    stop = plan.option_stop if plan else entry * 0.68
    target = plan.option_sell if plan else entry * 1.48
    outcome, exit_px, exit_date = simulate_hold(
        entry=entry, stop=stop, target=target, path=path, stop_on=stop_on
    )
    pnl_pct = pnl_lot = None
    if outcome != "MISSING" and entry > 0:
        pnl_pct = (exit_px - entry) / entry * 100.0
        qty = _lot_qty(row)
        if qty:
            pnl_lot = (exit_px - entry) * qty
    return BacktestTrade(
        signal_date=signal_date,
        exit_date=exit_date or (path[-1].date if path else ""),
        symbol=row.symbol,
        action=row.suggestion_action or "NONE",
        strike=float(row.suggestion_strike or 0),
        option_type=row.suggestion_option_type or "",
        expiry=str(row.expiry or ""),
        entry=entry,
        exit_px=exit_px,
        stop=stop,
        target=target,
        outcome=outcome,
        pnl_pct=pnl_pct,
        pnl_per_lot=pnl_lot,
        rank=rank,
        potential=potential,
        cover=row.suggestion_move_cover_ratio,
        label=row.suggestion_label,
    )


class BacktestService:
    """Replay High / Top-5 ideas on past EOD sessions."""

    def __init__(
        self,
        scanner: ScannerService | None = None,
        rules: RulesConfig | None = None,
    ) -> None:
        self.rules = rules or get_rules()
        self.scanner = scanner or ScannerService(self.rules)

    def _session_window(self, signal_sessions: int, hold: int) -> list[str]:
        need = signal_sessions + hold
        sessions = self.scanner.bhav.list_recent_sessions(
            need, calendar_lookback=max(60, need * 3)
        )
        return list(reversed(sessions))

    def _mode_notes(
        self, settings: BacktestSettings, *, take: int, hold: int
    ) -> list[str]:
        notes = [
            f"Mode {settings.mode}: Top {take}, hold {hold} session(s), "
            f"stop on {settings.stop_on}.",
            "EOD-to-EOD replay: enter at signal close. Not a live-fill backtest.",
            "OHLC is cut at the signal date (no future bars). Ban list is skipped historically.",
        ]
        if settings.mode == "strict":
            notes.append(
                f"Strict desk: cover ≥ {STRICT_DESK.min_cover}×, no OTM, "
                f"IV Rank < {STRICT_DESK.max_iv_rank}, no event in {STRICT_DESK.skip_event_days}d."
            )
        return notes

    def _picks_for_signal(
        self,
        symbols: list[SymbolMeta],
        *,
        signal: str,
        bhav: pd.DataFrame,
        nifty: pd.DataFrame | None,
        settings: BacktestSettings,
        take: int,
        only_top_n: bool,
    ) -> list[BuyPriority]:
        rows = self.scanner.scan_as_of(
            symbols, as_of_date=signal, bhav=bhav, nifty_ohlc=nifty
        )
        high = high_priority_ideas(rows)
        if settings.mode == "strict":
            high = rerank(
                [item for item in high if passes_strict_desk(item.row, settings)]
            )
        return top_buys(high, limit=take) if only_top_n else high

    def _hold_bhavs(
        self, sessions: list[str], signal: str, hold: int
    ) -> list[tuple[str, pd.DataFrame]]:
        start = sessions.index(signal) + 1
        path_bhavs: list[tuple[str, pd.DataFrame]] = []
        for exit_day in sessions[start : start + hold]:
            try:
                path_bhavs.append((exit_day, self.scanner.bhav.get_session_bhav(exit_day)))
            except Exception:
                continue
        return path_bhavs

    def _close_picks(
        self,
        picks: list[BuyPriority],
        *,
        signal: str,
        path_bhavs: list[tuple[str, pd.DataFrame]],
        settings: BacktestSettings,
    ) -> list[BacktestTrade]:
        trades: list[BacktestTrade] = []
        for item in picks:
            row = item.row
            path: list[SessionQuote] = []
            for exit_day, later in path_bhavs:
                quote = lookup_option_quote(
                    later,
                    symbol=row.symbol,
                    strike=float(row.suggestion_strike or 0),
                    option_type=row.suggestion_option_type or "",
                    expiry=str(row.expiry or ""),
                )
                if quote is None:
                    continue
                if not quote.date:
                    quote.date = exit_day
                path.append(quote)
            trade = close_trade(
                row,
                signal_date=signal,
                path=path,
                rank=item.rank,
                potential=item.potential,
                stop_on=settings.stop_on,
            )
            if not path:
                trade.outcome = "MISSING"
                trade.pnl_pct = None
                trade.pnl_per_lot = None
            trades.append(trade)
        return trades

    def run(
        self,
        symbols: list[SymbolMeta],
        *,
        signal_sessions: int = 10,
        settings: BacktestSettings | None = None,
        hold_sessions: int | None = None,
        top_n: int | None = None,
        only_top_n: bool = True,
    ) -> BacktestReport:
        settings = settings or STRICT_DESK
        hold = hold_sessions if hold_sessions is not None else settings.hold_sessions
        take = top_n if top_n is not None else settings.top_n
        sessions = self._session_window(signal_sessions, hold)
        notes = self._mode_notes(settings, take=take, hold=hold)
        if len(sessions) < hold + 1:
            return BacktestReport(
                signal_dates=[],
                hold_sessions=hold,
                mode=settings.mode,
                notes=notes + ["Not enough published bhav sessions to replay."],
            )

        signal_dates = sessions[:-hold][-signal_sessions:]
        nifty = self.scanner._fetch_nifty(False)
        trades: list[BacktestTrade] = []

        for signal in signal_dates:
            try:
                bhav = self.scanner.bhav.get_session_bhav(signal)
            except Exception as exc:
                notes.append(f"Skip {signal}: {exc}")
                continue
            picks = self._picks_for_signal(
                symbols,
                signal=signal,
                bhav=bhav,
                nifty=nifty,
                settings=settings,
                take=take,
                only_top_n=only_top_n,
            )
            trades.extend(
                self._close_picks(
                    picks,
                    signal=signal,
                    path_bhavs=self._hold_bhavs(sessions, signal, hold),
                    settings=settings,
                )
            )

        if len(self.scored_note(trades)) < 15:
            notes.append(
                "Sample is still small. Treat this as a check, not proof the method wins most of the time."
            )
        return BacktestReport(
            signal_dates=signal_dates,
            hold_sessions=hold,
            mode=settings.mode,
            trades=trades,
            notes=notes,
        )

    @staticmethod
    def scored_note(trades: list[BacktestTrade]) -> list[BacktestTrade]:
        return [t for t in trades if t.outcome != "MISSING" and t.pnl_pct is not None]
