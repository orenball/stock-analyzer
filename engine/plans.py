"""Stop-loss / take-profit levels and trade plans.

All levels are derived from volatility (ATR), recent swing lows, moving
averages and analyst targets. They are mechanical reference points, not advice.
"""


def _r(x):
    return round(float(x), 2)


def holding_plan(a, cost: float | None) -> dict:
    """Stop-loss and two take-profit levels for a stock you already own."""
    L, p = a.levels, a.price
    atr_ = L["atr"]
    # Stop: just under the 20-day swing low, kept between 1 and 3 ATR below price
    stop = min(p - atr_, max(p - 3 * atr_, L["swing_low20"] - 0.5 * atr_))
    risk = p - stop
    tp1 = p + 2 * risk  # 2:1 reward-to-risk: sell part here
    above = [x for x in (a.meta.get("targetMeanPrice"), L["high52"]) if x and x > tp1 * 1.02]
    # nearest real resistance beyond TP1, but never more than 4x the stop distance (old highs after a crash are unreachable)
    tp2 = min(min(above) if above else tp1 + risk, p + 4 * risk)
    notes = [
        f"Stop sits just below the 20-day swing low (${L['swing_low20']:.2f}), "
        f"{risk / atr_:.1f}× the stock's average daily range (ATR ${atr_:.2f}).",
        "Take profit 1 is twice the stop distance above the price: a common point to sell part of the position.",
        "Take profit 2 is the nearer of the analysts' mean target and the 52-week high above TP1, "
        "capped at four times the stop distance.",
    ]
    if cost is None:
        pass
    elif stop > cost:
        notes.insert(0, f"The stop is above your cost (${cost:.2f}), so it locks in a gain if hit.")
    elif p < cost:
        notes.insert(0, f"You are below cost; the stop caps the extra loss at {risk / p:.1%} from here.")
    return {"stop": _r(stop), "tp1": _r(tp1), "tp2": _r(tp2), "rr": round((tp1 - p) / risk, 1),
            "stop_pct": round(stop / p - 1, 4), "tp1_pct": round(tp1 / p - 1, 4), "tp2_pct": round(tp2 / p - 1, 4),
            "notes": notes}


def short_plan(a) -> dict:
    """1–30 day trade: tight ATR stop, 2:1 target, hold length from what drives the signal."""
    L, p = a.levels, a.price
    atr_ = L["atr"]
    stop = max(p - 1.5 * atr_, min(p - 0.75 * atr_, L["swing_low20"] - 0.25 * atr_))
    risk = p - stop
    target = max(p + 2 * risk, L["high20"] if L["high20"] > p + 1.5 * risk else 0)
    candle_driven = a.score_by("Candles") >= 1 and a.score_by("Technical") < 2
    days = "3–10 days" if candle_driven else "2–4 weeks"
    why = "candlestick reversal signals play out fast" if candle_driven else "trend and momentum signals need a few weeks"
    return {"entry": _r(p), "stop": _r(stop), "target": _r(target), "rr": round((target - p) / risk, 1),
            "stop_pct": round(stop / p - 1, 4), "target_pct": round(target / p - 1, 4),
            "hold": days, "hold_why": why}


def long_plan(a, high_risk: bool) -> dict:
    """3–24 month position: wide stop under the 200-day average, analyst-based target."""
    L, m, p = a.levels, a.meta, a.price
    mean_t = m.get("targetMeanPrice")
    if high_risk:
        stop = min(p * 0.88, max(p * 0.75, L["sma200"] * 0.92))
        target = min(mean_t, p * 1.6) if mean_t else p * 1.35  # consensus, capped: outlier highs skew it
        hold, why = "3–12 months", "volatile names move fast; reassess after each earnings report"
    else:
        stop = min(p * 0.92, max(p * 0.85, L["sma200"] * 0.95))
        target = min(mean_t, p * 1.3) if mean_t else p * 1.15
        hold, why = "12–24 months", "steady compounders need time; dividends add to the return"
    target = max(target, p * 1.05)
    return {"entry": _r(p), "stop": _r(stop), "target": _r(target), "rr": round((target - p) / (p - stop), 1),
            "stop_pct": round(stop / p - 1, 4), "target_pct": round(target / p - 1, 4),
            "hold": hold, "hold_why": why}
