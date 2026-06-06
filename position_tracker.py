"""
CLUELESS Indian Bot -- Position Tracker
========================================
Forked directly from CLUELESS US position_tracker.py to keep field names
identical (so the dashboard JS doesn't need to know which market it is).
Only changes from the US version:
  - INR currency formatting in Telegram alerts (₹ instead of $)
  - India flag prefix on alerts
  - NaN-safe JSON writer (the bug that took down CLUELESS US tonight)
  - .NS suffix awareness for ticker display (Yahoo keeps it, display strips it)

Stop rules (Darvas trailing, unchanged from US):
  Gain <  10%  : hold initial stop
  Gain >= 10%  : raise stop to breakeven (entry price)
  Gain >= 20%  : trailing stop 10% below running high
  Gain >= 30%  : trailing stop 7% below running high
"""

import os
import json
import math
import time
from datetime import datetime

import requests
import yfinance as yf
import pandas as pd


TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
SEND_TELEGRAM = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
POSITIONS_FILE = "positions.json"
STATE_FILE     = "positions_state.json"

# Same rules as CLUELESS US. The whole point is that Darvas math is universal.
STOP_RULES = [
    {"min_gain": 0,  "rule": "initial",    "trail_pct": None},
    {"min_gain": 10, "rule": "breakeven",  "trail_pct": None},
    {"min_gain": 20, "rule": "trail_10",   "trail_pct": 10.0},
    {"min_gain": 30, "rule": "trail_7",    "trail_pct":  7.0},
]


def script_path(name):
    return os.path.join(SCRIPT_DIR, name)


def bare_symbol(ticker):
    """Strip .NS suffix for display in alerts."""
    return ticker[:-3] if ticker.endswith(".NS") else ticker


def _clean_for_json(obj):
    """NaN-safe writer. NaN is not valid JSON; replace with None so JSON.parse() works."""
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: _clean_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean_for_json(v) for v in obj]
    return obj


def send_telegram(message):
    if not SEND_TELEGRAM:
        print("  (Telegram env vars missing -- skipping push)")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, data=payload, timeout=10)
        if r.status_code != 200:
            print(f"  Telegram send failed ({r.status_code}): {r.text[:200]}")
    except Exception as e:
        print(f"  Telegram send error: {e}")


def get_price_and_high(ticker):
    try:
        data = yf.download(ticker, period="5d", interval="1d",
                           progress=False, auto_adjust=False)
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        if data is None or data.empty:
            return None, None
        last = data.iloc[-1]
        close = float(last["Close"])
        high = float(last["High"])
        # Guard against NaN bars (pre-market manual runs, weekends, etc)
        if math.isnan(close) or math.isnan(high):
            return None, None
        return close, high
    except Exception as e:
        print(f"    yfinance failed for {ticker}: {e}")
        return None, None


def active_rule(gain_pct):
    rule = STOP_RULES[0]
    for r in STOP_RULES:
        if gain_pct >= r["min_gain"]:
            rule = r
    return rule


def compute_stop(pos, state):
    entry = pos["entry_price"]
    high = state.get("running_high", entry)
    high_gain_pct = (high - entry) / entry * 100
    rule = active_rule(high_gain_pct)

    if rule["rule"] == "initial":
        return pos["initial_stop"], "initial"
    if rule["rule"] == "breakeven":
        return max(entry, pos["initial_stop"]), "breakeven"

    trail_stop = high * (1 - rule["trail_pct"] / 100)
    prev_stop = state.get("current_stop", pos["initial_stop"])
    return max(trail_stop, prev_stop), rule["rule"]


def load_json(path, default):
    p = script_path(path)
    if not os.path.exists(p):
        return default
    try:
        with open(p, "r") as f:
            return json.load(f)
    except Exception:
        return default


def load_positions():
    data = load_json(POSITIONS_FILE, {})
    if isinstance(data, list):
        return data
    return data.get("positions", [])


def save_state(state):
    with open(script_path(STATE_FILE), "w") as f:
        json.dump(_clean_for_json(state), f, indent=2, default=str)


def track_position(pos, prev_state):
    raw_ticker = pos["ticker"].upper()
    # If user forgot the .NS suffix in positions.json, add it.
    if not raw_ticker.endswith(".NS") and not raw_ticker.endswith(".BO"):
        ticker = raw_ticker + ".NS"
    else:
        ticker = raw_ticker
    sym = bare_symbol(ticker)

    entry  = float(pos["entry_price"])
    shares = float(pos.get("shares", 0))
    initial_stop = float(pos["initial_stop"])

    price, day_high = get_price_and_high(ticker)
    if price is None:
        return prev_state, []

    prior_high = prev_state.get("running_high", entry)
    prior_stop = prev_state.get("current_stop", initial_stop)
    prior_milestone = prev_state.get("last_milestone", 0)
    prior_status = prev_state.get("status", "open")

    running_high = max(prior_high, day_high or price, price)
    current_stop, rule_name = compute_stop(
        pos, {"running_high": running_high, "current_stop": prior_stop}
    )

    gain_pct = (price - entry) / entry * 100
    high_gain_pct = (running_high - entry) / entry * 100
    pl_dollars = (price - entry) * shares  # field name kept for dashboard compat; values are INR

    alerts = []
    status = prior_status
    india_prefix = "\U0001F1EE\U0001F1F3 "

    # Stop hit
    if prior_status == "open" and price <= current_stop:
        status = "stopped"
        alerts.append(
            f"{india_prefix}\U0001F6A8 *STOP HIT \u2014 SELL {sym}*  `\u20B9{price:.2f}`\n\n"
            f"\u2022 Entry:  `\u20B9{entry:.2f}` ({pos.get('entry_date','')})\n"
            f"\u2022 Stop:   `\u20B9{current_stop:.2f}` ({rule_name})\n"
            f"\u2022 Outcome: *{gain_pct:+.1f}%*  (`\u20B9{pl_dollars:+.2f}`)\n"
            f"\u2022 High reached: `\u20B9{running_high:.2f}` (+{high_gain_pct:.1f}%)\n\n"
            f"Sell at Zerodha. Then remove {sym} from positions.json."
        )

    # Milestone alerts
    new_milestone = prior_milestone
    if status == "open":
        for m in (10, 20, 30):
            if gain_pct >= m and prior_milestone < m:
                new_milestone = m
                if m == 10:
                    alerts.append(
                        f"{india_prefix}\U0001F4C8 *{sym} +10%*  \u2014 stop moved to breakeven\n"
                        f"\u2022 Price: `\u20B9{price:.2f}` (entry `\u20B9{entry:.2f}`)\n"
                        f"\u2022 New stop: `\u20B9{current_stop:.2f}` (was `\u20B9{prior_stop:.2f}`)\n"
                        f"\u2022 You can no longer lose on this trade."
                    )
                elif m == 20:
                    alerts.append(
                        f"{india_prefix}\U0001F3AF *{sym} +20%*  \u2014 trailing stop active\n"
                        f"\u2022 Price: `\u20B9{price:.2f}`  P/L: `\u20B9{pl_dollars:+.2f}`\n"
                        f"\u2022 New stop: `\u20B9{current_stop:.2f}` (10% below running high)\n"
                        f"\u2022 Let it run. Don't touch it."
                    )
                elif m == 30:
                    alerts.append(
                        f"{india_prefix}\U0001F4B0 *{sym} +30%*  \u2014 decision point\n"
                        f"\u2022 Price: `\u20B9{price:.2f}`  P/L: `\u20B9{pl_dollars:+.2f}`\n"
                        f"\u2022 Stop tightened to `\u20B9{current_stop:.2f}` (7% trail)\n"
                        f"\u2022 Option A: take profit now.\n"
                        f"\u2022 Option B: let it run, stop protects gains."
                    )

    # Stop ratcheted up outside milestone moments
    if (status == "open"
            and current_stop > prior_stop * 1.01
            and new_milestone == prior_milestone):
        alerts.append(
            f"{india_prefix}\U0001F512 *{sym} stop raised*\n"
            f"\u2022 New stop: `\u20B9{current_stop:.2f}` (was `\u20B9{prior_stop:.2f}`)\n"
            f"\u2022 Price: `\u20B9{price:.2f}`  P/L: `\u20B9{pl_dollars:+.2f}`"
        )

    new_state = {
        "ticker": ticker,
        "entry_price": entry,
        "entry_date": pos.get("entry_date", ""),
        "shares": shares,
        "initial_stop": initial_stop,
        "last_price": round(price, 4),
        "running_high": round(running_high, 4),
        "current_stop": round(current_stop, 4),
        "stop_rule": rule_name,
        "gain_pct": round(gain_pct, 2),
        "high_gain_pct": round(high_gain_pct, 2),
        "pl_dollars": round(pl_dollars, 2),  # field name kept for dashboard compat; values are INR
        "last_milestone": new_milestone,
        "status": status,
        "last_checked": datetime.now().isoformat(timespec="seconds"),
        "notes": pos.get("notes", ""),
    }
    return new_state, alerts


def main():
    print("\n>>> CLUELESS India Position Tracker starting...\n")
    positions = load_positions()
    if not positions:
        print("No open positions in positions.json. Nothing to track.\n")
        save_state({"positions": [], "updated": datetime.now().isoformat(timespec="seconds")})
        return

    prev_full = load_json(STATE_FILE, {})
    prev_by_ticker = {p["ticker"]: p for p in prev_full.get("positions", [])}

    new_positions_state = []
    all_alerts = []

    for pos in positions:
        raw_ticker = pos["ticker"].upper()
        if not raw_ticker.endswith(".NS") and not raw_ticker.endswith(".BO"):
            lookup_ticker = raw_ticker + ".NS"
        else:
            lookup_ticker = raw_ticker
        sym = bare_symbol(lookup_ticker)

        print(f"  Tracking {sym}...", end=" ")
        prev = prev_by_ticker.get(lookup_ticker, {})
        # Also check old-format prior states (without .NS) in case user migrated
        if not prev and raw_ticker in prev_by_ticker:
            prev = prev_by_ticker[raw_ticker]

        state, alerts = track_position(pos, prev)
        new_positions_state.append(state)
        all_alerts.extend(alerts)
        print(f"{state['gain_pct']:+.2f}% ({state['stop_rule']}, "
              f"stop \u20B9{state['current_stop']:.2f})")
        if state["status"] == "stopped":
            print(f"    \u2757  {sym} STOP HIT")

    save_state({
        "positions": new_positions_state,
        "updated": datetime.now().isoformat(timespec="seconds"),
    })

    if all_alerts:
        print(f"\nSending {len(all_alerts)} alert(s) to Telegram...")
        for msg in all_alerts:
            send_telegram(msg)
            time.sleep(0.6)
    else:
        print("\nNo alerts this cycle.")

    print("\n" + "=" * 70)
    print(f"POSITION TRACKER  --  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)
    total_pl = 0.0
    for p in new_positions_state:
        mark = "\u2705" if p["status"] == "open" else "\U0001F6A8 STOPPED"
        sym = bare_symbol(p["ticker"])
        print(f"  {mark}  {sym:<10}  "
              f"entry \u20B9{p['entry_price']:.2f}  now \u20B9{p['last_price']:.2f}  "
              f"{p['gain_pct']:+.2f}%  stop \u20B9{p['current_stop']:.2f} "
              f"({p['stop_rule']})  P/L \u20B9{p['pl_dollars']:+.2f}")
        total_pl += p["pl_dollars"]
    print("-" * 70)
    print(f"  TOTAL UNREALIZED P/L: \u20B9{total_pl:+.2f}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
