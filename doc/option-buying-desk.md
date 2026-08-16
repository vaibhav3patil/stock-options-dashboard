# Option Buying Desk — product handbook

> Personal research desk for **NSE stock option buying** after the last close.  
> Long calls and puts only. **Not live quotes. Not a broker. Not investment advice.**

**Prefer the visual version?** Open [option-buying-desk.html](option-buying-desk.html) in a browser.

*Last updated: 16 August 2026*

---

## 1. What this application is

After the cash and F&O session is over, the desk answers four questions:

| Question | What you get |
|----------|----------------|
| Which stock? | A short **High-priority** list, plus a **Top 5** to compare first |
| Which side? | **BUY CALL** or **BUY PUT** |
| Which contract? | Expiry, strike type (ATM / slight ITM / slight OTM), last-close premium, **lot size** |
| How to manage it? | Research marks: **Buy · Sell · Stop**, margin %, reward-to-risk |

It is a **last-close research board**. You study it in the evening or before the next open, then place the trade yourself on your broker (for example Kite) at the **live** price of the **same strike and expiry**.

### In scope

- Indian **single-stock** F&O names
- **Buying** call or put options (you pay premium)
- Scoring from **yesterday’s close** (or the latest published session)
- Ranking which ideas look most realistic
- A simple plan: where you would buy, book, and cut

### Out of scope

- Live ticking prices or a live option chain
- Automatic orders
- Writing / selling options
- Index options (Nifty, Bank Nifty, …) as trade ideas
- A promise that High-priority names will win

A High name can still lose the **entire premium**. Treat every number as research, not an order ticket.

---

## 2. The one idea the desk is built on

Option buyers **pay premium and fight time**. A name is only interesting when three things line up:

1. **A real chance of a large-enough move** — the stock can travel farther than the option needs to break even.
2. **Affordable option prices** — implied volatility is not already “maxed out” for that move.
3. **A usable contract** — enough activity near the money that you can enter and exit without a lottery ticket.

In one line:

> **Liquid contract + affordable premium + a reason for a fast, large-enough move.**

Everything on the screen is a way to check those three.

---

## 3. How you use it (daily)

Think of it as an evening / pre-open ritual, not a day-trading terminal.

1. **Open the desk** in the browser.
2. Choose the universe in the sidebar:
   - **Fast scan on** — about **20 liquid large names** (faster, everyday use).
   - **Fast scan off** — the **full F&O stock list**, then still only High ideas are shown.
3. Click **Refresh scan**. Wait while last-close prices are scored.
4. Read the **market banner** (India vs the world — it only sizes stops/targets; it does not pick stocks).
5. Compare the **Top 5** side by side.
6. Check the **Strict desk** hint: which of those five would you actually buy if you were picky.
7. Open one name under **Look closer** for the plan, the “why”, nearby strikes, and the last-close chain window.
8. If you trade: buy **that strike and expiry** at the **next open’s live price**. Do not hunt a new ATM at 9:15 unless you mean to.

Optional: **Replay past sessions** in the sidebar to see how last-close picks behaved over recent days. Judge **average P&L**, not win rate alone.

The page **does not** show the full scanner of every name. Medium and Low ideas are hidden on purpose.

---

## 4. What “last close” means for you

| You see | It is |
|---------|--------|
| Spot / last close | The stock’s last official close |
| Option premium | The last traded / last-close premium of that contract |
| As-of date | The F&O session the whole board is using (same day for every column) |
| Saturday / Sunday / holiday | The desk rolls back to the **previous weekday session** |

There is **no live bid–ask** after the close. Check the spread on your broker at the open. If the spread is ugly, skip — the desk cannot see that overnight.

---

## 5. Universe — who can appear

- **Stocks only.** Index symbols are tagged and not treated as stock option ideas.
- **Fast list (typical everyday set):** Reliance, TCS, Infosys, HDFC Bank, ICICI Bank, SBI, Bharti Airtel, ITC, L&T, Axis Bank, Kotak Bank, Bajaj Finance, Maruti, Sun Pharma, Titan, Asian Paints, Wipro, HCL Tech, NTPC, Power Grid.
- **Full list:** every name on the F&O stock universe file the desk is configured with.

Being on the F&O list is **not** the same as being liquid *today*. Thin names fail the liquidity gate and never become High buys.

---

## 6. How a name is judged (selection criteria)

The desk walks each stock through **hard gates**, then a **direction**, then a **contract**, then a **priority rank**.

### 6.1 Hard skips (do not buy)

A name is **Skip** when any of these is true:

| Gate | Plain meaning |
|------|----------------|
| Missing or stale prices | Stock or option close is not usable |
| **F&O ban** | The name is on the ban list — no new F&O |
| **Dividend / split / bonus within 5 days** | Corporate-action window — skip naked buying |
| **Thin options** | Near-the-money volume or open interest too low (desk floor: about **500** contracts of volume and **2,000** OI in the ATM window) |
| **Premium too large for the book** | Cost per lot above the **₹15,000** research budget |
| **Only a far-OTM lottery** would fit | The desk prefers ATM / one strike in / one strike out |

### 6.2 Spread only (direction ok, do not buy naked)

The idea may still show a CALL/PUT, but readiness becomes **Spread only** when:

- Option prices look **rich vs recent actual movement** (implied vol much higher than realized vol), **or**
- **IV Rank is high** (about **50+** is already unfriendly for naked buys; **70+** is “rich”) unless the expected move is *clearly* larger than usual, **or**
- An **earnings / event sits inside the assumed hold** (about **2 sessions**), so crush risk is high.

“Spread only” means: if you still want the name, prefer a **defined-risk debit spread**, not a naked long premium.

### 6.3 Watch (incomplete)

Liquidity is acceptable, but:

- Expected move **does not cover** the break-even with a buffer, **or**
- There is **no clear direction** (no trend, no relative-strength tilt, no squeeze).

These names do **not** appear on the High board.

### 6.4 Ready to buy

Last-close liquidity looks fine, the move-vs-premium check passes, there is a directional or squeeze setup, and IV is not already eating the trade. This is the only readiness that is meant for a **naked** long call or put.

---

## 7. How CALL vs PUT is chosen

| Stock picture | Bias |
|---------------|------|
| Uptrend (price above the faster average, structure up) | **BUY CALL** |
| Downtrend | **BUY PUT** |
| Sideways, but clearly **stronger than Nifty** over ~20 sessions | CALL |
| Sideways, but clearly **weaker than Nifty** | PUT |
| No tilt | No buy idea |

A **squeeze** (the stock has been coiling) is a plus — buyers want expansion — but it does not flip the side by itself.

---

## 8. Which strike and expiry

The desk looks at the **near expiry** and three nearby strikes:

| Label | Meaning |
|-------|---------|
| **ATM** | Closest strike to last close — preferred |
| **ITM-1** | One strike in-the-money |
| **OTM-1** | One strike out-of-the-money |

It ranks them by: **cover** (can the typical move beat break-even?), liquidity, and whether cost/lot stays inside the budget. **ATM is preferred**, not hardcoded as the only answer.

**How you should trade the suggestion:** buy **that printed strike and expiry** at the next session’s live price. Do not reinterpret “ATM” as “whatever is ATM at 9:15”.

---

## 9. Breakeven, cover, and lot

These three numbers decide whether a contract is even worth ranking.

**Break-even (to expiry, idealised)**

- Call BE = **strike + premium**
- Put BE = **strike − premium**

**Cover** = expected move ÷ points needed to reach BE.  
Expected move uses the stock’s typical daily range (ATR) over a short hold (about **2 sessions**).

| Cover | Reading |
|-------|---------|
| **≥ 2.0×** | Strong — typical range has room |
| **≥ 1.5×** | Healthy — this is the desk’s main bar |
| **1.0–1.5×** | Tight — easy to miss |
| **< 1.0×** | The typical move may never reach BE |

**Lot** is the NSE board lot. **Cost / lot = lot × premium.** If that cost is above the research budget, the idea is not treated as a clean naked buy.

---

## 10. High priority and Top 5

Every remaining BUY CALL / BUY PUT gets a **potential** score from 0–100. This is *“how realistic is a path to profit?”*, not a forecasted return.

**What lifts potential**

- Readiness = Ready to buy
- Cover ≥ 1.5× (especially ≥ 2×)
- A 1-ATR day in the right direction still shows a profit on the option
- Higher last-close composite score
- Livelier ATR%
- ATM (slight ITM is fine; OTM is penalised)
- Squeeze + trend / relative strength aligned with the side
- Easy need-to-BE (about 1% or less)
- Low IV Rank

**What hurts potential**

- Watch / spread-only readiness
- Cover below 1×
- 1-ATR day still below BE
- OTM strike
- Need-to-BE about 3% or more
- IV Rank 50–70 (worse above 70)
- Event within 5 days (worse within 2)

**Bands**

| Potential | Band | On the page? |
|-----------|------|----------------|
| **70 and above** | High | Yes — this is the board |
| 50–69 | Medium | Hidden |
| Below 50 | Low | Hidden |

**Top 5** = the first five High names after this ranking. Gold highlighting is “look here first”, not “buy all five”.

---

## 11. Strict desk vs “take the Top 5”

The compare board can show five names. **You should not force five tickets.**

**Strict desk** (what to actually consider buying):

- At most **Top 2**
- Cover **≥ 1.5×**
- **No OTM-1**
- IV Rank **below 50** (when rank is known)
- **No event in the next 2 days**
- If you replay history: hold about **4 sessions**, stop only on a **closing** print through the stop (not the day’s low wick)

If **none** of the Top 5 pass Strict, the desk’s advice is **skip the session**.

**Wide desk** (older, looser replay): Top 5, 2-session hold, stop on the day’s low. Use it to study history, not as the live buying rule.

---

## 12. Buy · Sell · Stop (the trade plan)

These are **research marks from last close**, sized to the dated **market tape** on the banner (cautious / risk-on / risk-off). They are not live quotes.

| Tile | Meaning |
|------|---------|
| **Buy** | Last-close option premium |
| **Stop** | Cut if premium falls about this far (in a cautious tape, roughly **32%** of premium) |
| **Sell** | Book-profit mark: about **1.5×** the risk, **capped** if a typical 1-ATR day cannot fund a bigger target |
| **Margin %** | (Sell − Buy) ÷ Buy |
| **R:R** | Reward ÷ risk |
| **P&L / lot** | Profit if you hit Sell, in rupees per lot |
| **Stock stop / target** | Rough underlying levels (about 0.8 ATR against you; target near or beyond BE) |

Brokerage, STT, and slippage are **not** included. The tape on the banner is a **dated brief**, not a live news feed — when markets change, the brief should be refreshed so stops stay honest.

---

## 13. What each part of the screen is for

| Area | Use it to |
|------|-----------|
| **Hero + as-of date** | Confirm you are looking at the latest F&O close, not a stale Thursday on a Saturday |
| **Market banner** | Know if stops are tight (cautious) or more generous |
| **Counts** | How many names were scored vs how many made High / Top 5 |
| **Top 5 compare** | Scan the same session across columns; green = best in that row |
| **Strict desk line** | The 0–2 names worth a real ticket |
| **High table** | Sortable list of every High idea (download as CSV if you want) |
| **This name’s plan** | Buy / sell / stop tiles, expiry P&L scenarios, nearby strikes |
| **Why this stock** | Readiness, why-text, warnings, failed checks, rule checklist |
| **Option chain** | Last-close ATM-window rows — not live |

---

## 14. Backtest — “did last-close picks work?”

**Replay past sessions** walks recent closes as if you had run the desk then, takes the High (or Strict) picks, and scores what that **same contract** did over the hold.

| Number | How to read it |
|--------|----------------|
| Signals | How many past closes were replayed |
| Trades scored | How many had a later price to judge |
| Win rate | Share that finished green — **not** the main score |
| **Avg P&L** | The number that matters (a few big losers can wreck a 50% win rate) |
| Target / stop | How often the plan’s sell vs stop was tagged first |

This is **close-to-close research**, not a live-fill backtest. Small samples are a check, not proof.

---

## 15. Word list

| Word | Meaning on this desk |
|------|----------------------|
| **ATR** | Typical daily range of the stock (about 14 days) |
| **ATR%** | That range as a % of last close — livelier names are friendlier to buyers |
| **HV** | How much the stock actually moved recently |
| **IV / ATM IV** | How expensive options are (estimated from the close) |
| **IV Rank** | Where today’s IV sits vs its own recent history (low = cheaper than usual) |
| **RS** | Relative strength vs Nifty — leaders for calls, laggards for puts |
| **Squeeze** | The stock has been coiling; expansion would help a buyer |
| **PCR** | Put/call open-interest context — never a buy signal by itself |
| **DTE** | Days to expiry |
| **Score** | 0–100 last-close composite (setup + liquidity + IV vs HV) |
| **Potential** | 0–100 “can this option realistically get to profit?” |
| **Cover** | Expected move ÷ need-to-BE |
| **BE** | Expiry break-even of the suggested strike |

---

## 16. Common ways this desk is misread

- Treating **High** as “must buy five names”.
- Buying a **new ATM** at 9:15 instead of the printed strike.
- Ignoring **cover** and buying cheap OTM because the premium “feels affordable”.
- Buying into **rich IV** the day before results.
- Holding a weekly with **no move** and hoping time will help (it will not).
- Forgetting **lot × premium** until after you are in.
- Using the board as **live** prices.

---

## 17. Disclaimer

This handbook describes a **personal research tool**. Options can expire worthless. Data can be late or wrong. Nothing here is a recommendation to buy or sell any security.
