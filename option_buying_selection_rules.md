# Stock Option Buying — Selection Techniques & Rules

Purpose: Reference ruleset for building a dashboard that scores / filters F&O stocks for **option buying** (long calls / long puts).

Scope: Stock selection and readiness filters. Strike/expiry sizing can use the same metrics but are secondary.

Last updated: 2026-08-14

---

## 1. Design goal (what “good” means)

A stock is suitable for option **buying** when:

1. A **directional or volatility-expansion** move is plausible and large enough to beat premium + spread costs.
2. Option contracts are **liquid** enough to enter/exit cleanly.
3. **Implied volatility is not already fully pricing** the expected move (unless the expected move is larger still).

Buyers pay premium and fight **theta**. Filters should optimize for move quality, IV affordability, and liquidity.

---

## 2. Core parameters (dashboard input fields)

### 2.1 Liquidity (hard filters — fail = exclude)

| ID | Parameter | Why it matters | Suggested dashboard rule |
|----|-----------|----------------|--------------------------|
| L1 | Option volume (near strikes / ATM) | Real trades vs stale quotes | Min daily option volume threshold (tune per universe) |
| L2 | Open interest (OI) | Depth / participation | Min OI on ATM ± N strikes |
| L3 | Bid–ask spread (% of premium or absolute) | Direct entry/exit cost | Prefer spread ≤ ~1–2% of mid premium on ATM; flag wide spreads |
| L4 | Lot size × premium (notional risk unit) | Capital / position sizing | Cap max premium cost per lot; flag oversized units |
| L5 | Strike continuum quality | Ability to choose ATM/OTM | Require quotes across multiple contiguous strikes |

**Dashboard status:** `PASS` / `FAIL` / `WARN`

### 2.2 Volatility (IV regime)

| ID | Parameter | Why it matters | Suggested dashboard rule |
|----|-----------|----------------|--------------------------|
| V1 | Implied volatility (IV) | Cost of options | Show current IV; compare vs history |
| V2 | Historical / realized vol (HV / RV) | Actual recent movement | Compare IV vs HV gap |
| V3 | IV Rank | IV vs lookback range | Prefer low–mid IV Rank for naked buys |
| V4 | IV Percentile | % of days IV was below current | Prefer low–mid IVP for naked buys |
| V5 | IV − HV (or IV/HV ratio) | Over/under pricing of moves | Warn when IV ≫ recent HV with no catalyst |
| V6 | Term structure (front vs next) | Event / near-term premium | Flag front-month IV spikes (event weeks) |

**Buyer-friendly:** low–mid IV Rank/Percentile + expected expansion.  
**Buyer-hostile:** high IV with catalyst already passed / no leftover catalyst (IV crush risk).

### 2.3 Underlying move quality

| ID | Parameter | Why it matters | Suggested dashboard rule |
|----|-----------|----------------|--------------------------|
| M1 | ATR (points) | Typical range size | Display ATR and ATR% |
| M2 | ATR % of spot | Comparability across stocks | Prefer higher ATR% for buyers |
| M3 | Avg true daily range vs premium | Can move beat option cost? | Expected move ≥ break-even move needed by premium |
| M4 | Trend strength (e.g. ADX, HH/HL) | Sustained directional drift | Score trend strength |
| M5 | Beta / index sensitivity | Market-day expansion odds | Optional rank factor |
| M6 | Gap / news reactivity | Jump risk / opportunity | Tag reactive names |

**Sanity rule (M3):** If ATM (or chosen) option needs ~1.5–2× ATR within the holding window to profit after spread, mark as **poor naked-buy candidate**.

### 2.4 Price structure / technical setup

| ID | Parameter | Call bias | Put bias |
|----|-----------|-----------|----------|
| T1 | Trend / structure | Uptrend, pullback held, breakout | Downtrend, failed bounce, breakdown |
| T2 | Relative strength vs Nifty | Outperformer | Underperformer |
| T3 | Volume on break / fail | Expansion volume confirmation | Expansion volume confirmation |
| T4 | Range regime | Squeeze → expansion preferred | Squeeze → expansion preferred |
| T5 | Location in range | Breakout / support hold | Breakdown / resistance reject |

**Avoid for naked buys:** mid-range chop; late chase after a large already-extended candle with no continuation plan.

### 2.5 Catalysts & calendar

| ID | Parameter | Dashboard use |
|----|-----------|---------------|
| C1 | Earnings / results date | Event countdown; IV behavior tags |
| C2 | Sector / macro event | Session catalysts |
| C3 | Corporate actions / peer news | Ad-hoc tags |
| C4 | Days to expiry (DTE) | Match hold horizon; avoid “theta death” mismatch |
| C5 | F&O expiry week flag | Liquidity/IV anomaly awareness |

### 2.6 Positioning / flow

| ID | Parameter | Notes |
|----|-----------|-------|
| P1 | Call OI change + price | Rising price + call OI build → bullish participation |
| P2 | Put OI change + price | Falling price + put OI build → bearish participation |
| P3 | OI walls / max-pain proximity | Near expiry pinning risk for OTM lottery strikes |
| P4 | Unusual options activity | Requires liquidity + news confirmation |
| P5 | PCR | Context-dependent; not a standalone buy signal |

### 2.7 Greeks implications (for readiness, not stock identity)

| ID | Parameter | Buyer implication |
|----|-----------|-------------------|
| G1 | Delta availability (ATM / slight ITM liquid) | Prefer liquid ATM/near-ATM over far OTM |
| G2 | Theta burden vs DTE | Short thesis window if weekly/high theta |
| G3 | Vega / IV crush risk | High IV + post-event = hostile to longs |
| G4 | Gamma (near expiry ATM) | Pays only if move comes soon |

### 2.8 Capital & portfolio geometry

| ID | Parameter | Dashboard use |
|----|-----------|---------------|
| K1 | Premium × lot | Risk unit |
| K2 | Max risk per trade % | Position size gate |
| K3 | Correlation to open book | Avoid stacking same-sector clones |
| K4 | Defined-risk alternative flag | If premium rich → suggest debit spread instead of reject-only |

---

## 3. Techniques (implement as dashboard modules / scores)

### Technique A — Liquidity screen first
**Type:** Hard filter  
**Logic:** Keep only names with tight ATM bid–ask, meaningful volume/OI, stable multi-strike quotes.  
**Output:** Include / Exclude  
**Depends on:** L1–L5

### Technique B — IV Rank filter for buys
**Type:** Soft/hard filter + score  
**Logic:** Prefer low–mid IV Rank/Percentile with expansion setup; de-prioritize very high IV Rank for naked buys unless expected move ≫ IV.  
**Output:** Score + WARN on rich IV  
**Depends on:** V1–V6, C1–C5

### Technique C — Move vs premium sanity check
**Type:** Hard/soft gate  
**Logic:** Compare expected move over hold period (ATR/event-based) to option break-even move (premium + spread).  
**Output:** PASS if expected move covers break-even with buffer; else FAIL/WARN  
**Depends on:** M1–M3, L3, L4, C4

### Technique D — Relative strength / weakness scan
**Type:** Rank / score  
**Logic:** Rank F&O stocks vs Nifty (and sector). Calls on RS leaders breaking out; puts on RS laggards breaking down.  
**Output:** RS rank + call/put bias  
**Depends on:** T1–T3, M5

### Technique E — Volatility contraction → expansion
**Type:** Setup detector  
**Logic:** Detect coil/squeeze (low ATR / BB squeeze), IV not extreme, then breakout with volume → directional buy candidate.  
**Output:** Setup flag `SQUEEZE_BREAKOUT`  
**Depends on:** M1–M2, T3–T5, V3–V4

### Technique F — Catalyst map
**Type:** Calendar overlay  
**Logic:** Shortlist names with known dates; only buy pre-event if IV not maxed, else prefer defined-risk.  
**Output:** Catalyst tag + IV suitability  
**Depends on:** C1–C5, V3–V4, K4

### Technique G — Trend day / momentum continuation
**Type:** Intraday/swing setup  
**Logic:** Value acceptance one way (e.g. VWAP hold), index aligned or independent strength, short holding period.  
**Output:** Momentum long/short option bias  
**Depends on:** T1–T3, L1–L3, C4

### Technique H — Anti lottery-OTM filter
**Type:** Hard filter / education gate  
**Logic:** Reject or heavily penalize far-OTM-only “affordable” trades on low-ATR names. If only far OTM fits budget, stock/lot is usually wrong for naked buying.  
**Output:** FAIL / severe score penalty  
**Depends on:** G1, M2–M3, L4, K1

### Technique I — Sector confirmation
**Type:** Confirmation score  
**Logic:** Stock breakout/breakdown + sector basket confirmation raises continuation odds.  
**Output:** Sector confirm boolean / score boost  
**Depends on:** T2, sector returns breadth

### Technique J — Post-event IV crush filter
**Type:** Hard/soft filter  
**Logic:** After earnings/events, IV often collapses. Avoid fresh naked buys into rich-IV post-event drift unless IV already crushed and a new setup exists.  
**Output:** WARN/FAIL around event window  
**Depends on:** C1, V1–V4, V6

---

## 4. Pre-trade checklist (dashboard checklist widget)

Use as boolean gates before enabling a “Buy Call/Put” action:

1. [ ] **Liqudity OK** — chain liquid today (spread, volume, OI)
2. [ ] **IV regime OK** — IV Rank/Percentile acceptable for long premium
3. [ ] **Catalyst or technical expansion present**
4. [ ] **Expected move ≥ premium break-even** (with buffer)
5. [ ] **Trend / RS aligned** with call or put direction
6. [ ] **Lot × premium is a sensible risk unit**
7. [ ] **DTE matches thesis horizon** (theta won’t dominate first)
8. [ ] **Invalidation level defined** on the stock chart

**Aggregate rule:** If 2+ of {liquidity, IV, expected move} fail → do **not** allow naked option buy on that stock.

---

## 5. Suggested scoring model (for later dashboard)

Tune weights after backtesting; start simple.

| Component | Weight (draft) | Notes |
|-----------|----------------|-------|
| Liquidity score (L1–L5) | 25% | Hard floor: score 0 ⇒ exclude |
| IV suitability (V3/V4/V5) | 20% | Invert: lower IV Rank better for naked buys |
| Move vs premium (M3) | 20% | Critical edge check |
| Setup quality (T + E/G) | 20% | Breakout / RS / squeeze |
| Catalyst alignment (F/J) | 10% | Boost or penalize |
| Sector confirm (I) | 5% | Tie-breaker |

**Outputs per stock:**

- `eligibility`: EXCLUDE | NAKED_BUY_OK | SPREAD_ONLY | WATCH
- `direction_bias`: CALL | PUT | NEUTRAL
- `score`: 0–100
- `failed_rules`: [ids…]
- `warnings`: [ids…]

**Example eligibility mapping:**

- Liquidity fail → `EXCLUDE`
- Liquidity pass + IV rich + catalyst → `SPREAD_ONLY` (or EXCLUDE for naked)
- Liquidity pass + IV OK + move/premium fail → `WATCH` / `EXCLUDE`
- All key gates pass + setup → `NAKED_BUY_OK`

---

## 6. Universe notes (NFO)

- Prefer liquid large caps / active beta names when setup + IV agree.
- Midcaps: situational only (volume/OI surge + clean breakout + tight spreads).
- Usually poor for naked buying: thin OI, wide spreads, tiny ATR vs premium, extreme IV with no leftover catalyst.
- Index names in a stock list (e.g. NIFTY, BANKNIFTY) should be tagged separately from single-stock options.

---

## 7. Common failure modes (dashboard warning copy)

- In F&O list ≠ liquid option chain today
- High-IV event crush after buying
- Illiquid midcap wide spreads
- Holding weeklies too long with no move
- Ignoring lot size until after entry
- Treating single-stock options like index options
- Far OTM lottery tickets on low-ATR names

---

## 8. Implementation backlog (for dashboard build)

Data needed per symbol (near month unless noted):

- [ ] Spot, ATR, ATR%, beta, RS vs Nifty / sector
- [ ] IV, HV, IV Rank, IV Percentile, term structure
- [ ] ATM option volume, OI, bid, ask, mid, lot size
- [ ] Premium break-even move estimate
- [ ] Earnings/event calendar + DTE
- [ ] OI change, PCR, unusual activity flags
- [ ] Technical setup tags (trend, squeeze, breakout)
- [ ] Sector breadth confirmation

Rule engine:

- [ ] Implement Technique A–J as named rules with IDs
- [ ] Hard filters vs soft scores
- [ ] Eligibility state machine
- [ ] Checklist widget bound to rule IDs
- [ ] Config file for thresholds (so tuning doesn’t require code edits)

---

## 9. Threshold config placeholders

Fill with your brokerage data / backtests later:

```yaml
liquidity:
  min_option_volume: null          # TODO
  min_atm_oi: null                 # TODO
  max_bid_ask_pct_of_mid: 0.02     # draft
move_vs_premium:
  min_expected_move_to_be_ratio: 1.5  # draft (expected / break-even)
iv:
  max_iv_rank_naked_buy: 50        # draft
  max_iv_percentile_naked_buy: 50  # draft
  rich_iv_rank_warn: 70            # draft
positioning:
  max_premium_per_lot: null        # TODO (INR)
  max_risk_per_trade_pct: null     # TODO
dte:
  min_dte: null                    # TODO
  max_dte: null                    # TODO
```

---

## 10. Bottom line (product copy)

For option **buying**, stock selection is:

**liquid chain + affordable IV + a reason for a fast, large-enough move.**

---

## 11. Appendix — Indian F&O additions (IN*) & v1 priority

Added for NSE single-stock option buying dashboards. Full build prompt: `PROMPT_option_buying_dashboard.md`.

### 11.1 New India-specific rules

| ID | Rule | Type |
|----|------|------|
| IN1 | F&O ban / ban-period securities | HARD exclude |
| IN2 | ASM / GSM / surveillance | WARN / soft exclude |
| IN3 | India VIX regime | Soft score / WARN |
| IN4 | Tag INDEX vs STOCK (different thresholds) | Tag + routing |
| IN5 | Futures vs spot basis (premium/discount) | Soft |
| IN6 | Corporate action window (bonus/split/rights/ex-div) | HARD/WARN |
| IN7 | Circuit proximity | HARD/WARN |
| IN8 | Cash volume / delivery% confirmation | Soft |
| IN9 | Expiry / DTE bucket discipline | Soft/HARD by config |
| IN10 | Risk budget (max premium/trade, max concurrent) | HARD for trade badge |
| IN11 | Prefer ATM ± 1–2 strikes (anti-lottery) | HARD preference |
| IN12 | Stale quote / data freshness guard | HARD |

### 11.2 De-prioritize in v1 (info only, not hard-fail)

- P3 Max pain (noisy for stock options)
- P4 Unusual options activity (needs paid flow data)
- M6 Gap reactivity (needs stable news feed)
- V6 Term structure (after front-month works)
- Technique I sector confirm, Technique G VWAP (v1.5+)

### 11.3 Free / freemium data sources (research)

| Need | Source |
|------|--------|
| Universe / lots | Kite instruments CSV |
| Equity OHLC | yfinance (`SYMBOL.NS`), nselib, nsefeed, NSE bhavcopy |
| Option chain / OI / IV | nsepython, nselib, aynse, indiaopt (unofficial NSE) |
| Ban / events / VIX | nselib, indian-corp-action |
| IV Rank history | Build yourself from EOD ATM IV cache (SQLite/Parquet) |
| Earnings calendar | nselib events, indian-corp-action, optional Drishti API |

**Note:** No official free NSE commercial API. Cache + rate-limit. Optional later: Kite Connect / Upstox for reliability.
