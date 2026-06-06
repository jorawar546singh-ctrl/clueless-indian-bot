# CLUELESS Indian Bot

Darvas-style breakout scanner for NSE (National Stock Exchange of India).
Forked from the US-market [CLUELESS scanner](https://github.com/jorawar546singh-ctrl/ttm-scanner).

## What it does

- Scans NIFTY 500 + NIFTY Smallcap 250 (~750 stocks) once per trading day
- Identifies Darvas-style breakouts: 14-day box top + 2x volume confirmation
- Tracks every alerted ticker post-breakout (streak tracker)
- Manages adaptive trailing stops on open positions
- Sends a single end-of-day Telegram digest at 4:00pm IST (30 min after close)
- Dashboard shows breakouts, trending watchlist, gainers since alert, and open positions

## What's different from CLUELESS US

| Thing | US (CLUELESS) | India (this repo) |
|---|---|---|
| Universe | Finviz + Yahoo most-active | NIFTY 500 + Smallcap 250 |
| Schedule | Hourly scan + EOD digest | Single EOD scan + digest |
| Currency | USD ($) | INR (₹) |
| Account default | $1800 | ₹25,000 |
| Fundamentals (ELITE tier) | Yes (via FMP) | Disabled (FMP coverage gaps for India) |
| Reference links | Finviz, Yahoo, TradingView | Screener.in, Yahoo, TradingView |
| Ticker suffix | None | `.NS` (e.g. `RELIANCE.NS`) |

## Setup

1. Create GitHub repo (public, no initialization)
2. Drop all files from this folder into the repo
3. Add secrets to repo settings → secrets → actions:
   - `TELEGRAM_BOT_TOKEN` (same token as CLUELESS)
   - `TELEGRAM_CHAT_ID` (same chat as CLUELESS)
4. Enable GitHub Pages on the repo (settings → pages → source: main branch / root)
5. Wait for first scheduled run, or trigger manually from Actions tab

## Daily flow

- **10:30 UTC (4:00pm IST / 4:30am Calgary)**: cron fires
- Scanner runs against NIFTY 500 + Smallcap 250
- Streak tracker updates state for previously-alerted tickers
- Position tracker checks any open positions for stop hits
- Telegram digest sent with new breakouts + watchlist changes
- All state committed back to repo

## When you wake up

- Check Telegram digest from overnight
- Open dashboard, scan trending watchlist for setups still developing
- If taking a trade: run position sizing math (2% account risk hard rule)
- Update `positions.json` with new entry
- Next day digest reflects the change

## Hard rules

1. **2% account risk per trade. Non-negotiable.**
2. **One position at a time at current account size.**
3. **Write a journal entry in `trades.md` after every closed trade.**
4. **No position sizing without running the formula first.**

These rules are inherited from CLUELESS US. They don't change just because the market changed.

## Universe fallback layers

The scanner uses 3 layers of fallback to build the scan universe:

1. **Live NSE archives** (best): Fetches current NIFTY 500 + Smallcap 250 from `nsearchives.nseindia.com`. ~750 tickers, always current.
2. **Bundled `data/nifty500.csv`** (fallback): 501-stock CSV bundled with this repo + ~40 recent NIFTY 500 additions hardcoded in `RECENT_ADDITIONS`. ~540 tickers. Refresh the CSV quarterly when NSE rebalances.
3. **Hardcoded `FALLBACK_UNIVERSE`** (last resort): ~150 liquid stocks baked into the Python script. Only used if `data/nifty500.csv` is missing.

You'll see which one was used in the workflow logs each run. If layer 1 keeps failing for weeks, refresh the bundled CSV from NSE's website.
