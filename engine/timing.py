"""How long a take-profit level usually takes to reach, and whether today's price is a good one.

Both are estimates from the stock's own price history and public data, not predictions.
"""
import numpy as np

from analysis import rsi

SIMS = 3000          # simulated price paths
MAX_DAYS = 504       # look up to two years (trading days) ahead
DRIFT_SHRINK = 0.5   # count only half of last year's trend: past returns overstate future ones
DRIFT_CAP = 0.30     # and never more than ±30% a year


def _r(x, nd=2):
    return round(float(x), nd)


def _paths(close, seed=7):
    """Bootstrap last year's daily moves into SIMS two-year price paths (as ratios to today's price).

    Keeps the stock's real volatility and fat tails; the trend is shrunk and capped so a hot
    year doesn't promise the same again.
    """
    rets = np.log(close).diff().dropna().iloc[-252:].to_numpy()
    mean = rets.mean()
    drift = np.clip(mean * DRIFT_SHRINK, -DRIFT_CAP / 252, DRIFT_CAP / 252)
    rng = np.random.default_rng(seed)
    sample = rng.choice(rets - mean + drift, size=(SIMS, MAX_DAYS), replace=True)
    return np.exp(np.cumsum(sample, axis=1)), drift * 252


def _cal(days):
    """Trading days → rough calendar wording."""
    if days is None:
        return None
    if days <= 7:
        return f"about {days} trading days"
    if days <= 30:
        n = round(days / 5)
        return f"about {n} week{'s' if n != 1 else ''}"
    n = round(days / 21)
    return f"about {n} month{'s' if n != 1 else ''}"


def reach_odds(paths, price, target, stop):
    """Chance the target is hit before the stop, and how many trading days that usually takes."""
    up, down = target / price, stop / price
    hit_up = paths >= up
    hit_dn = paths <= down
    first_up = np.where(hit_up.any(1), hit_up.argmax(1), MAX_DAYS + 1)
    first_dn = np.where(hit_dn.any(1), hit_dn.argmax(1), MAX_DAYS + 1)
    win = first_up < first_dn
    p_win = float(win.mean())
    if win.sum() < 30:  # too few successful paths to say how long it takes
        return {"p_target_first": round(p_win, 3), "median_days": None, "range_days": None,
                "typical": None}
    days = first_up[win] + 1
    med, lo, hi = (int(np.percentile(days, q)) for q in (50, 25, 75))
    return {"p_target_first": round(p_win, 3), "median_days": med, "range_days": [lo, hi],
            "typical": _cal(med), "range_text": f"{_cal(lo)} to {_cal(hi)}"}


def take_profit_times(a, plans):
    """Add time-to-target estimates to every take-profit level in the plans dict (in place)."""
    paths, drift_used = _paths(a.history["Close"])
    p = a.price
    for key, plan in plans.items():
        if not plan:
            continue
        stop = plan["stop"]
        if "target" in plan:
            plan["target_time"] = reach_odds(paths, p, plan["target"], stop)
        for tp in ("tp1", "tp2"):
            if tp in plan:
                plan[f"{tp}_time"] = reach_odds(paths, p, plan[tp], stop)
    return {"method": "3,000 simulated paths built from the last year of daily moves; "
                      "trend counted at half and capped at ±30%/yr; closing prices only",
            "annual_drift_used": round(float(drift_used), 3)}


def price_check(a):
    """Is this a good price? Two separate questions:
    value  = is the company cheap or expensive for what it earns and is expected to be worth
    timing = is today a good moment to buy, or is the price stretched short term
    """
    m, L, p = a.meta, a.levels, a.price
    value, timing = [], []

    # --- Value
    fpe, peg = m.get("forwardPE"), m.get("trailingPegRatio") or m.get("pegRatio")
    if fpe and fpe > 0:
        pts = 1 if fpe < 15 else 0 if fpe <= 30 else -0.5 if fpe <= 45 else -1
        word = "cheap" if fpe < 15 else "normal" if fpe <= 30 else "rich" if fpe <= 45 else "very expensive"
        value.append({"text": f"Forward P/E {fpe:.1f}: {word} (cheap < 15, normal 15–30, rich 30–45, very expensive > 45)", "points": pts})
    elif m.get("trailingPE") is None and m.get("forwardPE") is None:
        value.append({"text": "No P/E: the company has no profits yet, or it's an ETF/fund, so value is judged on analyst targets only", "points": 0})
    if peg and peg > 0:
        pts = 1 if peg < 1 else 0 if peg <= 2 else -0.5 if peg <= 3 else -1
        word = "cheap for its growth" if peg < 1 else "fair for its growth" if peg <= 2 else "pricey for its growth" if peg <= 3 else "expensive for its growth"
        value.append({"text": f"PEG {peg:.2f}: {word} (P/E divided by growth; under 1 is cheap)", "points": pts})
    tgt, n = m.get("targetMeanPrice"), m.get("numberOfAnalystOpinions") or 0
    if tgt and n >= 3:
        up = tgt / p - 1
        pts = 1 if up > 0.2 else 0.5 if up > 0.08 else -1 if up < -0.05 else 0
        lo, hi = m.get("targetLowPrice"), m.get("targetHighPrice")
        rng = f" (range ${lo:.0f}–${hi:.0f})" if lo and hi else ""
        value.append({"text": f"{n} analysts' average target ${tgt:.2f}{rng}: {up:+.0%} from here", "points": pts})

    # --- Timing
    r = float(rsi(a.history["Close"]).iloc[-1])
    pts = 1 if r < 35 else -1 if r > 70 else -0.5 if r > 62 else 0
    timing.append({"text": f"RSI {r:.0f}: " + ("oversold, sellers look exhausted" if r < 35 else "overbought, it has run up fast" if r > 70
                   else "getting hot" if r > 62 else "calm, neither overbought nor oversold"), "points": pts})
    sma200, sma50 = L["sma200"], L["sma50"]
    stretch = p / sma200 - 1
    pts = -1 if stretch > 0.30 else -0.5 if stretch > 0.15 else 0.5 if stretch >= 0 else 0
    timing.append({"text": f"{stretch:+.0%} vs the 200-day average (${sma200:.2f}): " + (
        "far above its long-term trend, pullbacks are common from here" if stretch > 0.30 else
        "well above its long-term trend" if stretch > 0.15 else
        "close above its long-term trend, a healthy spot" if stretch >= 0 else
        "below its long-term trend: cheaper, but the trend is weak"), "points": pts})
    pos = (p - L["low52"]) / (L["high52"] - L["low52"]) if L["high52"] > L["low52"] else 0.5
    pts = -0.5 if pos > 0.9 else 0
    timing.append({"text": f"At {pos:.0%} of its 52-week range (${L['low52']:.2f}–${L['high52']:.2f})"
                   + (": buying near the top of the year" if pos > 0.9 else ""), "points": pts})

    v = sum(x["points"] for x in value)
    t = sum(x["points"] for x in timing)
    if v >= 1 and t >= 0:
        label = "GOOD PRICE: reasonable valuation and a fair entry point"
    elif v >= 1:
        label = "GOOD VALUE, STRETCHED ENTRY: the company looks fairly priced, but the stock has run up; a pullback would be a better entry"
    elif v <= -1 and t >= 0:
        label = "EXPENSIVE: the chart is fine, but you are paying a lot for the business"
    elif v <= -1:
        label = "EXPENSIVE AND STRETCHED: pricey business and an extended chart"
    elif t < 0:
        label = "FAIR VALUE, STRETCHED ENTRY: not cheap or expensive, but it has run up short term"
    else:
        label = "FAIR PRICE: nothing stands out as cheap or expensive"

    # A calmer entry level: the 50-day average when the stock is well above it, else today's price.
    better = None
    if t < 0 and p > sma50 * 1.03:
        better = {"price": _r(sma50), "pct": round(sma50 / p - 1, 4),
                  "why": "the 50-day average, where pullbacks in an uptrend often find buyers"}
    return {"label": label, "value_points": v, "timing_points": t,
            "value": value, "timing": timing, "better_entry": better}
