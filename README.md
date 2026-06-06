# CLUELESS Indian Bot

Darvas-style breakout scanner for NSE (National Stock Exchange of India).
Forked from the US-market [CLUELESS scanner](https://github.com/jorawar546singh-ctrl/ttm-scanner).

## What it does

- Scans NIFTY 500 (~500 stocks) once per trading day
- Identifies Darvas-style breakouts: 14-day box top + 2x volume confirmation
- Tracks every alerted ticker post-breakout (streak tracker)
- Manages adaptive trailing stops on open positions
- Sends a single end-of-day Telegram digest at 4:00pm IST (30 min after close)
- Dashboard shows trending watchlist (with FRESH badge on today's breakouts), weekly biggest gainers, and open positions

## What's different from CLUELESS US

| Thing | US (CLUELESS) | India (this repo) |
|---|---|---|
| Universe | Finviz + Yahoo most-active | NIFTY 500 |
| Schedule | Hourly scan + EOD digest | Single EOD scan + digest |
| Currency | USD ($) | INR (₹) |
| Account default | $1800 | ₹25,000 |
| Fundamentals (ELITE tier) | Yes (via FMP) | Disabled (FMP coverage gaps for India) |
| Reference links | Finviz, Yahoo, TradingView | Screener.in, Yahoo, TradingView |
| Ticker suffix | None | `.NS` (e.g. `RELIANCE.NS`) |

## Universe: why NIFTY 500 only

NIFTY 500 is the top 500 stocks on NSE by market cap. It covers ~96% of total
NSE market capitalization. The bottom of NIFTY 500 already extends into real
small-cap territory (~₹2,000-5,000 crore market cap), so this is NOT just a
"large caps" list — you're getting large, mid, AND small caps.

**Why we don't expand beyond NIFTY 500 at this stage:**

- NIFTY Smallcap 250 is a strict subset of NIFTY 500 (ranks 251-500 within it).
  Fetching it adds zero new tickers.
- Stocks below NIFTY 500 (microcaps, SME platform, etc.) carry liquidity and
  manipulation risks the Darvas signal doesn't handle well. Volume surges in
  microcaps are more often operator pumps than institutional accumulation.
- 500 stocks already produces ~5-15 breakout candidates per day.
- After 30+ trades on this universe, we can review the data and decide
  whether to expand to NIFTY Midcap 150 / Microcap 250 etc.

### Fallback layers

The scanner uses 3 layers to build the scan universe:

1. **Live NSE archives** (best): fetches current NIFTY 500 from
   `nsearchives.nseindia.com`. Always current.
2. **Bundled `data/nifty500.csv`** (fallback): 501-stock CSV in this repo +
   ~40 recent additions hardcoded in `RECENT_ADDITIONS`. Refresh quarterly.
3. **Hardcoded `FALLBACK_UNIVERSE`** (last resort): ~150 liquid stocks baked
   into the Python script. Only used if `data/nifty500.csv` is missing.

Workflow logs show which layer was used.

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
- Scanner runs against NIFTY 500
- Streak tracker updates state for previously-alerted tickers + flags today's new breakouts
- Position tracker checks any open positions for stop hits
- Telegram digest sent with new breakouts + watchlist changes
- All state committed back to repo

## When you wake up

- Check Telegram digest from overnight
- Open dashboard → **Trending Watchlist** is sorted with today's NEW breakouts pinned at the top (green badge, slight green tint)
- Older streaks that are still trending appear below
- **Biggest Gainers Since Alert** (default: 7-day window) shows what's worked
- If taking a trade: run position sizing math (2% account risk hard rule)
- Update `positions.json` with new entry
- Next day digest reflects the change

## Hard rules

1. **2% account risk per trade. Non-negotiable.**
2. **One position at a time at current account size.**
3. **Write a journal entry in `trades.md` after every closed trade.**
4. **No position sizing without running the formula first.**

These rules are inherited from CLUELESS US. They don't change just because the market changed.
