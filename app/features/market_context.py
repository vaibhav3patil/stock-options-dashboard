"""Dated India + global market regime used to size targets and stops."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketContext:
    as_of: str
    regime: str  # RISK_ON | CAUTIOUS | RISK_OFF
    headline: str
    nifty: str
    global_note: str
    sl_frac: float  # stop as fraction of option premium
    reward_multiple: float  # target = risk × this
    underlying_atr_stop: float  # SL distance in ATRs
    note: str


# Last researched close: 14 Aug 2026
# India: Nifty 24,366 (−0.12%), Sensex 78,009 (−0.09%), range-bound 24,200–24,500.
# Global: Wall Street record (S&P 7,799) on soft US inflation / Fed hold odds;
# Asia firmer; Europe softer. Crude ~$87, US–Iran / Hormuz risk, FII selling, INR ~95.4.
CURRENT_MARKET = MarketContext(
    as_of="2026-08-14",
    regime="CAUTIOUS",
    headline="India closed flat-to-weak while Wall Street hit records — geo and crude cap risk appetite.",
    nifty="Nifty 24,366 (−0.12%) · Sensex 78,009 (−0.09%) · India VIX eased on the close",
    global_note=(
        "S&P 500 record 7,799 after soft US inflation (Fed hike less likely). "
        "Asia stronger; Europe weaker. Brent ~$87 on US–Iran / Hormuz blockade talk. "
        "FIIs sold; rupee ~95.42. Metals/pharma/cement weak; durables bid."
    ),
    sl_frac=0.32,
    reward_multiple=1.5,
    underlying_atr_stop=0.80,
    note=(
        "Cautious regime: tighter option stop (~32% of premium), take profit at 1.5R, "
        "do not stretch for 2R while Nifty is stuck 24,200–24,500 and crude/geo can spike."
    ),
)


def get_market_context() -> MarketContext:
    return CURRENT_MARKET
