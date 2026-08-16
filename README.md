# Option Buying Dashboard (NSE F&O)

Personal research tool for **stock option buying** on the Indian NSE F&O universe: pick names, suggest **BUY CALL / BUY PUT + strike**, rank **High-priority** ideas, and show **buy / sell / stop**, **lot size**, and profit margin from **last market close**.

**How the desk works (functional handbook):** open [doc/option-buying-desk.html](doc/option-buying-desk.html) in a browser, or read [doc/option-buying-desk.md](doc/option-buying-desk.md). Selection criteria, High / Top 5, Strict desk, and the on-screen words are all there.

**Design:** Daily / pre-market selection from **last close** — not live ticks.

## Disclaimer

This is a personal research/educational tool, **not** investment advice. NSE unofficial endpoints can break or ban IPs. Options trading can cause total loss of premium. No warranty of data accuracy or trading results.

## What “last close” means

| Input | Source | Notes |
|------|--------|-------|
| Equity OHLC / ATR / HV / RS / squeeze | yfinance daily bars | Spot = last close |
| Option OI, volume, close premium, PCR | NSE F&O EOD bhavcopy (`nsearchives`) | One file for whole universe |
| Lot size | Bhav `NewBrdLotQty` (fallback: Kite instruments) | Shown on Trade idea + High table |
| ATM IV + IV Rank | Black–Scholes on close; daily history on disk | High IV Rank → SPREAD_ONLY (V3) unless cover is extra strong |
| F&O ban | NSE ban list (`nselib`) | IN1 → EXCLUDE |
| Earnings / corp actions | `data/events.csv` override, else yfinance | Event in hold window → SPREAD_ONLY (C1); div/split/bonus ≤5d → EXCLUDE (C3) |
| Bid–ask (L3) | Not in EOD bhav | Skipped after close — check spread on Kite at open |

## Setup

```bash
cd option_dashboard
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app/streamlit_app.py
```

Open `http://localhost:8501`. Use **Fast scan** for the liquid 20, or turn it off for the full F&O stock list. After a scan the page shows **High-priority buys** and a **Top 5**, not the full scanner.

## Deploy

Restart the Streamlit **process** on every release (new container / `systemctl restart` / new Cloud run). Do not hot-swap code into a long-lived worker — that is what left an old scanner in memory and broke backtest.

Set `APP_VERSION` (or `GIT_SHA`) to the image tag or commit so the sidebar shows which build is running.

```bash
export APP_VERSION="$(git rev-parse --short HEAD)"
streamlit run app/streamlit_app.py
```

The scanner object is **not** cached across reruns. Bhav/OHLC stay on disk under `data/cache/`. `watchdog` is required so file changes reload the whole app.

## Tests

```bash
pytest tests/ -q
```

## Docs

| File | Contents |
|------|----------|
| [doc/option-buying-desk.html](doc/option-buying-desk.html) | Visual product handbook (open in a browser) |
| [doc/option-buying-desk.md](doc/option-buying-desk.md) | Same handbook in markdown |
| [doc/README.md](doc/README.md) | Doc index |
| [option_buying_selection_rules.md](option_buying_selection_rules.md) | Builder rule IDs (L1, M3, IN12, …) — not needed to *use* the desk |
| `rules.yaml` | Thresholds (liquidity, ATR, risk budget) |

## Limits

- Bhavcopy appears after the session (typically evening); weekends/holidays walk back to the prior session.
- Live option-chain is **not** called. Pick after the close; place the trade at the next open on Kite.
- Market regime text is a dated snapshot in code, not a live news feed.
