"""
CLUELESS Indian Bot -- Darvas Breakout Scanner for NSE
======================================================
Forked from CLUELESS US (ttm_scanner.py). Same core logic, adapted for:
  - NIFTY 500 + NIFTY Smallcap 250 universe (~750 stocks)
  - .NS ticker suffix for Yahoo Finance
  - INR pricing
  - Screener.in / TradingView links
  - No FMP fundamentals layer (Indian coverage is unreliable; pure technical)

Scoring rubric is unchanged from US version. A Darvas box is a Darvas box.
"""
import time, os, json, re
from datetime import datetime
import requests
import pandas as pd
import yfinance as yf

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
SEND_TELEGRAM = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)

# --- Scan parameters (INR pricing) ---
DARVAS_BOX_DAYS = 14
VOLUME_MULTIPLIER = 2.0
MIN_PRICE = 50.0      # ₹50 minimum (excludes penny stocks)
MAX_PRICE = 5000.0    # ₹5000 maximum (above this, ₹25k account can barely buy 1 share)
TOP_N_TO_SHOW = 15    # Slightly higher than US since we scan more tickers
DEDUP_HOURS = 24      # Once per day so dedup is largely moot, but kept defensive

# --- File paths ---
DEDUP_FILE = "alerted.log"
LATEST_JSON = "latest.json"
HISTORY_JSON = "history.json"
ALERTED_HISTORY = "alerted_history.json"
HISTORY_RETENTION_DAYS = 180

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# NSE archives URLs for index constituents
NIFTY_500_URL = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"

# Static fallback CSV (bundled in repo as data/nifty500.csv).
# Refresh quarterly: https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv
NIFTY_500_STATIC_CSV = os.path.join("data", "nifty500.csv")

# Recent NIFTY 500 additions (post-2022) likely missing from the bundled static CSV.
# These get merged in when the static fallback is used.
RECENT_ADDITIONS = [
    "ZOMATO", "NYKAA", "PAYTM", "POLICYBZR", "DELHIVERY", "LICI", "MAPMYINDIA",
    "TATATECH", "MANKIND", "JIOFIN", "ADANIENSOL", "PHOENIXLTD", "PRESTIGE",
    "SUZLON", "IREDA", "RVNL", "IRFC", "RAILTEL", "MAZDOCK", "BSE",
    "CDSL", "ANGELONE", "IEX", "KPITTECH", "TATAELXSI", "PERSISTENT",
    "ROUTE", "TANLA", "TATAINVEST", "POONAWALLA", "AUBANK", "BANDHANBNK",
    "EASEMYTRIP", "SBFC", "FIVESTAR", "AAVAS", "HOMEFIRST", "RBA",
    "PIRAMALENT", "SIEMENS", "ABB", "TIINDIA", "POLYCAB", "HAVELLS",
    "INDIGO", "JUBLFOOD", "DEVYANI", "JUBLINGREA", "VARUNBEV", "SAPPHIRE",
    "TRENT", "ABFRL", "DMART", "DIXON", "AMBER", "BLUESTARCO",
    "SONACOMS", "DATAPATTNS", "HAPPSTMNDS", "ZENSARTECH", "BIRLASOFT",
    "INOXWIND", "WAAREE", "PREMIERENE", "ASTERDM", "MEDPLUS",
]

# Fallback list of liquid NSE stocks if NSE archives are unreachable.
# Covers a meaningful slice of NIFTY 500 + Smallcap 250 so scanner still works.
FALLBACK_UNIVERSE = [
    # Large caps
    "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY", "HINDUNILVR", "ITC", "SBIN",
    "BHARTIARTL", "KOTAKBANK", "LT", "AXISBANK", "BAJFINANCE", "ASIANPAINT", "MARUTI",
    "HCLTECH", "SUNPHARMA", "TITAN", "ULTRACEMCO", "WIPRO", "NESTLEIND", "POWERGRID",
    "NTPC", "ONGC", "TATAMOTORS", "M&M", "ADANIENT", "JSWSTEEL", "TATASTEEL", "COALINDIA",
    "BAJAJFINSV", "TECHM", "INDUSINDBK", "GRASIM", "BPCL", "DIVISLAB", "DRREDDY", "EICHERMOT",
    "BRITANNIA", "CIPLA", "HEROMOTOCO", "BAJAJ-AUTO", "HDFCLIFE", "SBILIFE", "ADANIPORTS",
    "APOLLOHOSP", "TATACONSUM", "HINDALCO", "UPL", "SHRIRAMFIN", "LTIM",
    # Mid caps
    "PIDILITIND", "GODREJCP", "DABUR", "MARICO", "COLPAL", "BERGEPAINT", "TRENT", "DMART",
    "VEDL", "JINDALSTEL", "SAIL", "NMDC", "IGL", "GAIL", "PETRONET", "INDIGO", "JUBLFOOD",
    "DIXON", "POLYCAB", "ABBOTINDIA", "MPHASIS", "PERSISTENT", "COFORGE", "MINDTREE",
    "LICHSGFIN", "BANKBARODA", "PNB", "CANBK", "IDFCFIRSTB", "FEDERALBNK", "RBLBANK",
    "AUBANK", "BANDHANBNK", "SRTRANSFIN", "MUTHOOTFIN", "MFSL", "CHOLAFIN", "SBICARD",
    "CDSL", "MCX", "BSE", "NSE", "ANGELONE", "IEX",
    "MAZDOCK", "BEL", "HAL", "BHEL", "BHARATFORG", "SIEMENS", "ABB", "CUMMINSIND",
    "VOLTAS", "HAVELLS", "CROMPTON", "WHIRLPOOL", "AMBER", "BLUESTARCO",
    "PAGEIND", "BATAINDIA", "RELAXO", "VIPIND", "TRIDENT", "WELSPUNIND",
    # Small caps with liquidity
    "KPITTECH", "TATAELXSI", "INTELLECT", "TANLA", "ROUTE", "BIRLASOFT", "SONACOMS",
    "ZOMATO", "PAYTM", "NYKAA", "POLICYBZR", "MAPMYINDIA", "EASEMYTRIP", "DELHIVERY",
    "ABCAPITAL", "ABFRL", "MANAPPURAM", "PNBHOUSING", "REPCOHOME", "CANFINHOME",
    "GUJGASLTD", "MGL", "AEGISCHEM", "GNFC", "DEEPAKNTR", "AARTIIND", "TATACHEM",
    "AAVAS", "HOMEFIRST", "FIVESTAR", "SBFC", "PIRAMALENT", "SUNDARMFIN",
    "RVNL", "IRCTC", "IRFC", "RAILTEL", "CONCOR", "GMRINFRA", "IRB",
    "OFSS", "AFFLE", "HAPPSTMNDS", "ZENSARTECH", "FIRSTSOURCE", "DATAPATTNS",
    "DEVYANI", "JUBLINGREA", "VARUNBEV", "SAPPHIRE", "DODLA", "HERITAGE",
]


def script_path(name):
    return os.path.join(SCRIPT_DIR, name)


# ============================================================
# Universe acquisition
# ============================================================
def fetch_nse_index(url, label):
    """
    Fetch an NSE index constituents CSV. Returns list of bare symbols (no suffix yet).
    NSE CSV format: Company Name, Industry, Symbol, Series, ISIN Code
    """
    try:
        # NSE sometimes requires a session-cookie warm-up; fetch homepage first
        s = requests.Session()
        s.headers.update(DEFAULT_HEADERS)
        try:
            s.get("https://www.nseindia.com", timeout=10)
        except Exception:
            pass

        r = s.get(url, timeout=20)
        if r.status_code != 200:
            print(f"    [{label}] HTTP {r.status_code} -- using fallback")
            return None

        symbols = []
        lines = r.text.strip().split("\n")
        for line in lines[1:]:  # skip header
            # CSV may have quoted fields with commas inside company names
            # Use the 3rd column position after splitting carefully
            parts = [p.strip().strip('"') for p in line.split(",")]
            if len(parts) >= 3:
                # Symbol is typically position 2 (0-indexed)
                sym = parts[2]
                # Some CSVs may have shifted columns -- accept anything that looks like a ticker
                if sym and sym.replace("-", "").replace("&", "").isalnum() and 1 <= len(sym) <= 20:
                    symbols.append(sym)

        if not symbols:
            print(f"    [{label}] parsed 0 symbols -- using fallback")
            return None

        print(f"    [{label}] {len(symbols)} symbols")
        return symbols
    except Exception as e:
        print(f"    [{label}] failed: {e}")
        return None


def load_static_csv():
    """Layer 2 fallback: load NIFTY 500 from bundled data/nifty500.csv."""
    path = os.path.join(SCRIPT_DIR, NIFTY_500_STATIC_CSV)
    if not os.path.exists(path):
        return None
    try:
        symbols = []
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().strip().split("\n")
        for line in lines[1:]:  # skip header
            parts = [p.strip().strip('"') for p in line.split(",")]
            if len(parts) >= 3:
                sym = parts[2]
                if sym and sym.replace("-", "").replace("&", "").isalnum():
                    symbols.append(sym)
        return symbols if symbols else None
    except Exception as e:
        print(f"    [static CSV] load failed: {e}")
        return None


def get_all_candidates():
    """
    Build the scan universe with 3-layer fallback:
      1. Live NSE archives (NIFTY 500) -- current as of today
      2. Bundled data/nifty500.csv + RECENT_ADDITIONS -- reliable floor
      3. Hardcoded FALLBACK_UNIVERSE -- last resort

    Note: NIFTY Smallcap 250 is a strict SUBSET of NIFTY 500 (it's the bottom-
    250 by market cap *within* NIFTY 500). Fetching it adds no new tickers --
    it just gets de-duped away. Scanning NIFTY 500 covers the entire mid+
    smallcap range you can responsibly trade at a small account size.
    """
    print("Building NSE scan universe...")
    nifty500 = fetch_nse_index(NIFTY_500_URL, "NIFTY 500")

    raw = []
    if nifty500: raw.extend(nifty500)

    if not raw:
        # Layer 2: bundled static CSV + recent additions
        static = load_static_csv()
        if static:
            print(f"  [static CSV] {len(static)} symbols + {len(RECENT_ADDITIONS)} recent additions")
            raw = static + RECENT_ADDITIONS
        else:
            # Layer 3: hardcoded list (only if even the bundled CSV is missing)
            print("  All fetches failed -- using hardcoded FALLBACK_UNIVERSE")
            raw = FALLBACK_UNIVERSE

    # Dedup and add .NS suffix for yfinance
    seen = set()
    tickers = []
    for sym in raw:
        if sym not in seen:
            seen.add(sym)
            tickers.append(f"{sym}.NS")

    print(f"  Universe size: {len(tickers)} tickers (de-duped)\n")
    return tickers


# ============================================================
# Darvas breakout check (unchanged from US version)
# ============================================================
def check_darvas_breakout(ticker):
    try:
        data = yf.download(ticker, period="60d", interval="1d",
                           progress=False, auto_adjust=False)
    except Exception:
        return None
    if data is None or len(data) < DARVAS_BOX_DAYS + 5:
        return None
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    today = data.iloc[-1]
    today_close = float(today["Close"])
    today_volume = float(today["Volume"])
    if not (MIN_PRICE <= today_close <= MAX_PRICE):
        return None

    prior = data.iloc[-(DARVAS_BOX_DAYS + 1):-1]
    box_top = float(prior["High"].max())
    box_bottom = float(prior["Low"].min())
    if today_close <= box_top:
        return None

    vol_lookback = min(20, len(data) - 1)
    avg_vol = float(data["Volume"].iloc[-(vol_lookback + 1):-1].mean())
    if avg_vol <= 0 or today_volume < avg_vol * VOLUME_MULTIPLIER:
        return None

    vol_ratio = today_volume / avg_vol
    pct_above_box = (today_close - box_top) / box_top * 100
    closes = data["Close"].astype(float)
    ma20 = float(closes.iloc[-20:].mean())
    ma20_prev = float(closes.iloc[-21:-1].mean())
    ma_rising = ma20 > ma20_prev
    box_range_pct = (box_top - box_bottom) / box_top * 100
    stop = box_top * 0.98
    target = today_close * 1.30
    risk = today_close - stop
    reward = target - today_close
    rr_ratio = reward / risk if risk > 0 else 0
    risk_pct = risk / today_close * 100
    spark = [round(float(x), 2) for x in closes.iloc[-30:].tolist()]

    hit = {
        "ticker": ticker, "price": round(today_close, 2),
        "box_top": round(box_top, 2), "box_bottom": round(box_bottom, 2),
        "pct_above_box": round(pct_above_box, 2),
        "vol_today": int(today_volume), "vol_avg_20d": int(avg_vol),
        "vol_ratio": round(vol_ratio, 2),
        "suggested_stop": round(stop, 2), "target_30pct": round(target, 2),
        "risk_pct": round(risk_pct, 2), "rr_ratio": round(rr_ratio, 2),
        "box_range_pct": round(box_range_pct, 2), "ma20": round(ma20, 2),
        "ma_rising": ma_rising,
        "price_vs_ma20_pct": round((today_close - ma20) / ma20 * 100, 2),
        "spark": spark,
    }
    hit.update(score_breakout(hit))
    return hit


def score_breakout(h):
    """Identical scoring to US version. A Darvas box is a Darvas box."""
    v = h["vol_ratio"]
    vol_score = 20 if v >= 5 else 18 if v >= 4 else 14 if v >= 3 else 11 if v >= 2.5 else 8 if v >= 2 else 4
    p = h["pct_above_box"]
    clarity_score = 20 if p >= 6 else 16 if p >= 4 else 13 if p >= 2.5 else 10 if p >= 1.5 else 6 if p >= 0.5 else 3
    r = h["box_range_pct"]
    box_score = 20 if r <= 10 else 16 if r <= 15 else 12 if r <= 20 else 8 if r <= 25 else 5 if r <= 35 else 2
    rr = h["rr_ratio"]
    rr_score = 20 if rr >= 5 else 16 if rr >= 4 else 12 if rr >= 3 else 8 if rr >= 2 else 5 if rr >= 1.5 else 2
    pct_ma = h["price_vs_ma20_pct"]; rising = h["ma_rising"]
    if rising and pct_ma >= 10:  trend_score = 20
    elif rising and pct_ma >= 5: trend_score = 16
    elif rising and pct_ma >= 0: trend_score = 12
    elif rising:                 trend_score = 8
    elif pct_ma >= 5:            trend_score = 8
    elif pct_ma >= 0:            trend_score = 5
    else:                        trend_score = 2

    total = vol_score + clarity_score + box_score + rr_score + trend_score
    if total >= 90:   grade, tier, emoji = "A+", "CLEAN", "\U0001F7E2"
    elif total >= 85: grade, tier, emoji = "A",  "CLEAN", "\U0001F7E2"
    elif total >= 75: grade, tier, emoji = "B+", "SOLID", "\U0001F7E1"
    elif total >= 70: grade, tier, emoji = "B",  "SOLID", "\U0001F7E1"
    elif total >= 60: grade, tier, emoji = "C+", "MARGINAL", "\U0001F7E0"
    elif total >= 55: grade, tier, emoji = "C",  "MARGINAL", "\U0001F7E0"
    else:             grade, tier, emoji = "D",  "WEAK", "\U0001F534"
    return {"score": total, "grade": grade, "tier": tier, "emoji": emoji,
        "score_breakdown": {"volume": vol_score, "clarity": clarity_score,
            "box_quality": box_score, "risk_reward": rr_score, "trend": trend_score}}


# ============================================================
# De-dup + alerted history (NaN-safe writer applied here)
# ============================================================
def load_recent_alerts():
    recent = set(); path = script_path(DEDUP_FILE)
    if not os.path.exists(path): return recent
    cutoff = time.time() - (DEDUP_HOURS * 3600)
    try:
        with open(path) as f:
            for line in f:
                parts = line.strip().split(",")
                if len(parts) == 2 and float(parts[0]) >= cutoff:
                    recent.add(parts[1])
    except Exception: pass
    return recent


def record_alerts(tickers):
    now = time.time()
    with open(script_path(DEDUP_FILE), "a") as f:
        for t in tickers:
            f.write(f"{now},{t}\n")


def _parse_iso(s):
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def update_alerted_history(hits):
    """30-day rolling record of every alerted breakout."""
    from datetime import timedelta
    path = script_path(ALERTED_HISTORY)
    history = []
    if os.path.exists(path):
        try:
            with open(path) as f:
                history = json.load(f)
        except Exception:
            history = []

    cutoff = datetime.now() - timedelta(days=HISTORY_RETENTION_DAYS)
    history = [h for h in history if _parse_iso(h.get("first_alerted")) and
               _parse_iso(h["first_alerted"]) >= cutoff]
    existing = {h["ticker"]: h for h in history}

    for hit in hits:
        t = hit["ticker"]
        if t in existing:
            continue
        existing[t] = {
            "ticker": t,
            "first_alerted": datetime.now().isoformat(timespec="seconds"),
            "breakout_price": hit["price"],
            "breakout_box_top": hit["box_top"],
            "original_grade": hit["grade"],
            "original_tier": hit["tier"],
            "original_score": hit["score"],
        }

    with open(path, "w") as f:
        json.dump(list(existing.values()), f, indent=2, default=str)


# ============================================================
# Telegram (India-prefixed messages, INR formatting, Screener.in links)
# ============================================================
def send_telegram(message):
    if not SEND_TELEGRAM:
        print("  (Telegram env vars missing -- skipping push)")
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


def bare_symbol(ticker):
    """Strip .NS suffix for display."""
    return ticker[:-3] if ticker.endswith(".NS") else ticker


def format_telegram_message(h):
    sb = h["score_breakdown"]
    sym = bare_symbol(h["ticker"])
    return (
        f"\U0001F1EE\U0001F1F3 *INDIA* \u00B7 {h['emoji']} *{h['tier']}* \u2022 *{sym}*  "
        f"`\u20B9{h['price']}`  *[{h['grade']} \u2022 {h['score']}/100]*\n\n"
        f"*Technical:*\n"
        f"\u2022 Volume: `{sb['volume']}/20`  ({h['vol_ratio']}\u00D7 avg)\n"
        f"\u2022 Clarity: `{sb['clarity']}/20`  (+{h['pct_above_box']}% above box)\n"
        f"\u2022 Box quality: `{sb['box_quality']}/20`\n"
        f"\u2022 Risk/reward: `{sb['risk_reward']}/20`  ({h['rr_ratio']}:1)\n"
        f"\u2022 Trend: `{sb['trend']}/20`\n\n"
        f"*Trade plan:*\n"
        f"\u2022 Entry:  `\u20B9{h['price']}`\n"
        f"\u2022 Stop:   `\u20B9{h['suggested_stop']}`  \u2192 risk `{h['risk_pct']}%`\n"
        f"\u2022 Target: `\u20B9{h['target_30pct']}`  \u2192 reward `+30%`\n\n"
        f"[Screener](https://www.screener.in/company/{sym}/)  "
        f"\u00B7  [Chart](https://finance.yahoo.com/quote/{h['ticker']})  "
        f"\u00B7  [TV](https://www.tradingview.com/symbols/NSE-{sym}/)"
    )


def format_summary_message(hits):
    lines = [f"\U0001F1EE\U0001F1F3 *INDIA SCAN* \u2014 {len(hits)} breakout(s)\n"]
    for h in hits:
        sym = bare_symbol(h["ticker"])
        lines.append(f"{h['emoji']} `{h['grade']:>2}` \u2022 *{sym:<12}* "
                     f"`\u20B9{h['price']:>8}` \u2022 {h['score']}")
    clean = [h for h in hits if h["tier"] == "CLEAN"]
    lines.append("")
    if clean:
        lines.append(f"\U0001F4A1 *Primary candidates:* " +
                     ", ".join(f"*{bare_symbol(h['ticker'])}*" for h in clean))
    else:
        lines.append("\u26A0 No CLEAN setups this run. Be selective.")
    return "\n".join(lines)


# ============================================================
# Dashboard output
# ============================================================
def write_dashboard_data(hits):
    now_iso = datetime.now().isoformat(timespec="seconds")
    payload = {
        "timestamp": now_iso, "count": len(hits), "hits": hits,
        "settings": {
            "box_days": DARVAS_BOX_DAYS, "vol_multiplier": VOLUME_MULTIPLIER,
            "min_price": MIN_PRICE, "max_price": MAX_PRICE,
            "sources": ["NIFTY 500", "NIFTY Smallcap 250"],
            "currency": "INR", "market": "NSE",
        }
    }
    with open(script_path(LATEST_JSON), "w") as f:
        json.dump(payload, f, indent=2, default=str)

    history = []
    hist_path = script_path(HISTORY_JSON)
    if os.path.exists(hist_path):
        try:
            with open(hist_path) as f: history = json.load(f)
        except Exception: history = []
    history.insert(0, {
        "timestamp": now_iso, "count": len(hits),
        "tickers": [bare_symbol(h["ticker"]) for h in hits],
        "clean_count": sum(1 for h in hits if h["tier"] == "CLEAN"),
    })
    history = history[:50]
    with open(hist_path, "w") as f:
        json.dump(history, f, indent=2, default=str)


def print_results(hits):
    if not hits:
        print("\nNo breakout setups found today. That's normal -- patience.")
        return
    print("\n" + "=" * 80)
    print(f"CLUELESS INDIA  --  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 80)
    for h in hits:
        sym = bare_symbol(h["ticker"])
        print(f"\n  [{h['grade']:>2}] {h['tier']:<8} {sym:<12}  "
              f"\u20B9{h['price']}  tech {h['score']}/100")


def main():
    print("\n>>> CLUELESS Indian Bot starting...\n")
    tickers = get_all_candidates()
    hits = []
    if tickers:
        print(f"Checking {len(tickers)} tickers for Darvas breakouts...\n")
        for i, t in enumerate(tickers, 1):
            print(f"  [{i}/{len(tickers)}] {bare_symbol(t)}...", end=" ")
            r = check_darvas_breakout(t)
            if r:
                print(f"BREAKOUT [{r['grade']}] {r['tier']} {r['score']}/100")
                hits.append(r)
            else:
                print("no")
            time.sleep(0.5)  # gentler rate limit; yfinance is more reliable for .NS

    hits = sorted(hits, key=lambda x: (x["score"], x["vol_ratio"]), reverse=True)[:TOP_N_TO_SHOW]

    print_results(hits)
    write_dashboard_data(hits)
    update_alerted_history(hits)

    if hits and SEND_TELEGRAM:
        recent = load_recent_alerts()
        new_hits = [h for h in hits if h["ticker"] not in recent]
        if new_hits:
            print(f"\nSending {len(new_hits)} alert(s)...")
            for h in new_hits:
                send_telegram(format_telegram_message(h))
                time.sleep(0.6)
            send_telegram(format_summary_message(new_hits))
            record_alerts([h["ticker"] for h in new_hits])
        else:
            print("\nAll hits were already alerted within the dedup window.")

    if hits:
        df_rows = [{k: v for k, v in h.items()
                    if k not in ("spark", "score_breakdown")} for h in hits]
        df = pd.DataFrame(df_rows)
        fn = script_path(f"breakouts_{datetime.now().strftime('%Y%m%d_%H%M')}.csv")
        df.to_csv(fn, index=False)
        print(f"CSV saved: {os.path.basename(fn)}\n")


if __name__ == "__main__":
    main()
