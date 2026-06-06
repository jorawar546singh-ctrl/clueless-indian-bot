# NaN Bug Fix for CLUELESS US (ttm-scanner)

## The bug

Your CLUELESS US dashboard shows "0 tracked" in the Trending Watchlist even though
`alerted_history.json` has 198 entries. The cause:

When `streak_tracker.py` runs at pre-market hours (or on weekends), yfinance returns
empty/NaN values for `today_close`. Python's `json.dump()` writes literal `NaN` tokens
to `streaks_state.json`, like:

```json
"today_close": NaN,
```

**`NaN` is not valid JSON.** JavaScript's `JSON.parse()` throws a SyntaxError on it
and bails silently. The dashboard then shows 0 entries because the parse failed.

## The fix

Add a NaN-safe writer to `streak_tracker.py`. Replace the existing `save_json` function
with this:

```python
import math

def _clean_for_json(obj):
    """Recursively replace NaN/Infinity with None so JSON.parse() doesn't choke."""
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: _clean_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean_for_json(v) for v in obj]
    return obj


def save_json(path, data):
    cleaned = _clean_for_json(data)
    with open(script_path(path), "w") as f:
        json.dump(cleaned, f, indent=2, default=str)
```

Also add an early guard in `analyze_streak()`:

```python
# After: today_close = float(today_row["Close"])
if math.isnan(today_close):
    return None
```

## Apply the same fix to `position_tracker.py` and `ttm_scanner.py`

The same pattern (`_clean_for_json` helper + use it in every `json.dump` call) belongs
in all three scripts. Otherwise the bug can reappear from a different file later.

## After applying the fix

1. Commit the changes
2. Manually trigger the workflow from the Actions tab
3. Wait for it to finish
4. Refresh dashboard

The watchlist should populate. If it still doesn't, check the "Run streak tracker"
step log -- the print output will show how many tickers were processed and which
were dropped, which narrows the diagnosis further.

## Why this also matters for the Indian scanner

The same NaN behavior happens with `.NS` tickers during Indian pre-market hours.
The Indian repo's `streak_tracker.py` and `position_tracker.py` already include
the `_clean_for_json` helper -- so this bug can't recur there.
