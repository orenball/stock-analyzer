"""Run the analysis engine on one ticker and print everything as JSON.

Usage (from the project folder):
    python engine/report.py TICKER            # analyze as a new buy
    python engine/report.py TICKER COST       # you own it, bought at COST per share

If no COST is given, the ticker is looked up in portfolio.json (optional).
Not found anywhere → it is analyzed as a stock you don't own.
"""
import json
import math
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent
ROOT = ENGINE.parent
sys.path.insert(0, str(ENGINE))

from analysis import analyze  # noqa: E402
from plans import holding_plan, long_plan, short_plan  # noqa: E402
from timing import flag_earnings, next_earnings, price_check, take_profit_times  # noqa: E402

CATEGORIES = ("Technical", "Candles", "Fundamental", "Analysts", "News")


def clean(x):
    """Make values JSON-safe: NaN/inf become None, numpy numbers become floats."""
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if hasattr(x, "item"):
        x = x.item()
    if isinstance(x, float) and not math.isfinite(x):
        return None
    return x


def find_cost(ticker):
    """Cost per share from portfolio.json, or None if the file or ticker is missing."""
    f = ROOT / "portfolio.json"
    if not f.exists():
        return None
    try:
        raw = json.loads(f.read_text())
    except json.JSONDecodeError:
        return None
    positions = raw.get("positions", []) if isinstance(raw, dict) else raw
    for p in positions:
        if str(p.get("ticker", "")).upper() == ticker and p.get("cost"):
            return float(p["cost"])
    return None


def call(a, owned):
    """Map the engine's own scores to one plain call. Thresholds match analysis.py."""
    if owned:
        return {"call": a.holding_verdict(), "basis": "holding_verdict(): score >= 5 stay/add, 0 to 5 stay, -3 to 0 review, < -3 consider exit"}
    s = a.score
    if s >= 5 and a.long_score >= 0:
        c = "BUY SIGNAL"
    elif s >= 5:
        c = "SHORT-TERM BUY SIGNAL ONLY (long-term signals are negative)"
    elif s >= 0:
        c = "WAIT / WATCHLIST: no strong reason to buy yet"
    else:
        c = "AVOID FOR NOW: most signals are negative"
    return {"call": c, "basis": "score >= 5 buy, 0 to 5 wait, < 0 avoid; long_score checks the long view"}


def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: report.py TICKER [COST]")
    ticker = sys.argv[1].upper().strip()
    cost, cost_source = None, None
    if len(sys.argv) > 2:
        try:
            cost, cost_source = float(sys.argv[2].replace("$", "").replace(",", "")), "argument"
        except ValueError:
            sys.exit(f"COST must be a number, got {sys.argv[2]!r}")
    else:
        cost = find_cost(ticker)
        cost_source = "portfolio.json" if cost else None

    a = analyze(ticker, with_news=True)
    if a.error:
        print(json.dumps({"ticker": ticker, "error": a.error}))
        return

    owned = cost is not None
    high_risk = (a.levels.get("vol") or 0) > 0.45 or (a.meta.get("beta") or 0) > 1.5
    out = {
        "ticker": a.ticker,
        "name": a.name,
        "price": a.price,
        "as_of": str(a.history.index[-1].date()),
        "score": a.score,
        "verdict": a.verdict,
        "short_score": a.short_score,
        "long_score": a.long_score,
        "horizon": a.holding_horizon,
        "score_by_category": {c: a.score_by(c) for c in CATEGORIES},
        "reasons": [{"category": r.category, "text": r.text, "points": r.points} for r in a.reasons],
        "meta": a.meta,
        "levels": a.levels,
        "high_risk": high_risk,
        "headlines": a.headlines[:8],
        "plans": {
            "short_trade": short_plan(a),
            "long_position": long_plan(a, high_risk),
        },
        "call": call(a, owned),
        "held": owned,
    }
    if owned:
        out["position"] = {
            "cost": cost,
            "cost_source": cost_source,
            "pl_pct": a.price / cost - 1,
            "plan": holding_plan(a, cost),
        }
    plans = dict(out["plans"])
    if owned:
        plans["holding"] = out["position"]["plan"]
    out["take_profit_timing"] = take_profit_times(a, plans)
    out["price_check"] = price_check(a)
    out["earnings"] = next_earnings(ticker)
    flag_earnings(plans, out["earnings"])
    print(json.dumps(clean(out), indent=2, default=str))


if __name__ == "__main__":
    main()
