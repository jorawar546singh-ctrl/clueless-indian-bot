"""
CLUELESS Indian Bot -- EOD Telegram Digest
===========================================
One consolidated message sent after the NSE close. Replaces the per-alert
spam pattern of the US scanner. Compact mobile-friendly format.
"""
import os, json
from datetime import datetime
import requests


TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
SEND_TELEGRAM = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def script_path(name):
    return os.path.join(SCRIPT_DIR, name)


def bare_symbol(ticker):
    return ticker[:-3] if ticker.endswith(".NS") else ticker


def load_json(path, default):
    p = script_path(path)
    if not os.path.exists(p):
        return default
    try:
        with open(p) as f:
            return json.load(f)
    except Exception:
        return default


def send_telegram(message):
    if not SEND_TELEGRAM:
        print("  (Telegram env vars missing -- skipping push)")
        print(message)
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": message,
                  "parse_mode": "Markdown", "disable_web_page_preview": True},
            timeout=10)
        if r.status_code != 200:
            print(f"  Telegram send failed ({r.status_code}): {r.text[:200]}")
    except Exception as e:
        print(f"  Telegram send error: {e}")


def build_digest():
    today = datetime.now().strftime("%a %d %b %Y")
    lines = [f"\U0001F1EE\U0001F1F3 *CLUELESS INDIA \u2014 EOD {today}*"]
    lines.append("")

    # --- Section 1: today's breakouts ---
    latest = load_json("latest.json", {"hits": []})
    hits = [h for h in latest.get("hits", []) if h.get("vol_ratio", 0) < 20]  # filter junk
    if hits:
        lines.append(f"*\U0001F525 Today's breakouts: {len(hits)}*")
        for h in hits[:10]:
            sym = bare_symbol(h["ticker"])
            lines.append(f"  {h.get('emoji', '')} `{h['grade']:>2}` *{sym:<12}* "
                         f"\u20B9{h['price']:>7}  ({h['score']}/100)")
        if len(hits) > 10:
            lines.append(f"  ...and {len(hits) - 10} more on dashboard")
    else:
        lines.append("*\U0001F525 Today's breakouts:* none")
    lines.append("")

    # --- Section 2: trending watchlist (top of streak state) ---
    streaks_state = load_json("streaks_state.json", {"streaks": []})
    streaks = streaks_state.get("streaks", [])
    trending = sorted(
        [s for s in streaks if s.get("status") == "trending"
         and s.get("current_streak", 0) >= 3],
        key=lambda x: x.get("current_streak", 0),
        reverse=True
    )[:10]
    if trending:
        lines.append(f"*\U0001F4C8 Trending now: {len(trending)}*")
        for s in trending:
            sym = bare_symbol(s["ticker"])
            vol_ok = "\u2705" if s.get("volume_ok_today") else " "
            box_ok = "\u2705" if s.get("new_box_break_today") else " "
            pct = s.get("pct_from_breakout", 0) or 0
            lines.append(f"  *{sym:<12}* day {s.get('days_since_breakout',0):>2}  "
                         f"streak {s.get('current_streak',0):>2}  "
                         f"{pct:+5.1f}%  V{vol_ok} B{box_ok}")
    lines.append("")

    # --- Section 3: open positions ---
    pos_state = load_json("positions_state.json", {"positions": []})
    open_positions = [p for p in pos_state.get("positions", []) if p.get("status") == "open"]
    if open_positions:
        lines.append(f"*\U0001F4BC Open positions: {len(open_positions)}*")
        for p in open_positions:
            sym = bare_symbol(p["ticker"])
            gain = p.get("gain_pct", 0) or 0
            pl = p.get("pl_dollars", 0) or 0
            lines.append(f"  *{sym:<12}* \u20B9{p.get('last_price',0):>7}  "
                         f"{gain:+5.1f}%  (P/L \u20B9{pl:+.2f})  "
                         f"stop \u20B9{p.get('current_stop',0)}")
    else:
        lines.append("*\U0001F4BC Open positions:* none")
    lines.append("")

    # --- Section 4: discipline reminder ---
    lines.append("_2% risk. One position. Journal every trade._")

    return "\n".join(lines)


def main():
    print("\n>>> Building EOD digest...\n")
    digest = build_digest()
    print(digest)
    print()
    send_telegram(digest)
    print("\nDigest sent.\n")


if __name__ == "__main__":
    main()
