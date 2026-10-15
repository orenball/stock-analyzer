---
name: analyze
description: "Full report on one stock or ETF: score, every reason behind it, trade levels, and a buy / wait / avoid call. Use for /analyze TICKER [COST], 'analyze X', 'check X', or 'should I buy X'."
---

# Analyze a stock

Runs the rule-based engine in `engine/` on one ticker and turns the result into a plain-language report. The skill adds no scoring rules of its own: every number and the call come from the engine.

## Steps

1. **Get the ticker** from the user's message (e.g. `/analyze NVDA`). If none is given, ask which one. Use Yahoo Finance symbols: `BRK-B`, `BTC-USD`, and a market suffix for non-US stocks (`TEVA.TA` Tel Aviv, `SAP.DE` Frankfurt, `7203.T` Tokyo).
2. **Get the cost, if any.** If the user gives a purchase price (`/analyze IREN 62.20`, "I bought at 62"), pass it as COST. Otherwise pass nothing: the script checks the optional `portfolio.json`, and if the ticker is not there it analyzes it as a new buy.
3. **Run the script** from the project root, with the project's virtual environment if there is one:
   - macOS / Linux: `.venv/bin/python engine/report.py TICKER [COST]`
   - Windows: `.venv\Scripts\python engine\report.py TICKER [COST]`
   - No `.venv` folder: set it up first as described in README.md ("Install"), then run.
   It prints JSON. If the JSON has `error`, explain it in one sentence (wrong symbol, not enough price history, no internet) and stop.
4. **Write the report** using only values from the JSON, in the format below. Never invent prices, targets or news.

## Report format

### 1. The call (one short block at the top)
- **Call:** `call.call`, in bold.
- **Score:** `score` → `verdict` (scale: ≥9 strong bullish, ≥5 bullish, between −3 and 5 neutral, ≤−3 bearish, ≤−6 strong bearish).
- **Horizon:** `horizon` (skip if "—").
- One sentence on *why*: the two or three reasons with the largest points, positive or negative.
- If `held` is true: say the user owns it, give `position.pl_pct` as a percent, and make clear the call is a stay/exit signal, not a buy signal.

### 2. Snapshot
A small table: name, price and `as_of` date, sector / industry, market cap (in $B), trailing and forward P/E, beta, dividend yield, 52-week high and low with distance from each, annual volatility (`levels.vol`), and the worst drop in the last year (`levels.max_drawdown`). Leave out rows whose value is null.

### 3. Why: the reasons
One table per category that has reasons, in this order: Technical, Candles, Fundamental, Analysts, News. Columns: signal (🟢 positive points, 🔴 negative, ⚪ zero), reason, points. Under each table: the category total from `score_by_category` and one plain sentence on what it means. Then the split: `short_score` (days to weeks: chart, candles, news) vs `long_score` (months to years: business, analysts, 200-day trend), and whether they agree.

### 4. Trade levels
- If held: `position.plan`: stop-loss, take-profit 1 and 2 (price and % from now), and its notes.
- If not held: both plans side by side: `plans.short_trade` and `plans.long_position` (entry, stop, target, reward-to-risk, hold time and the reason for it). Say whether the stock was treated as high-risk (`high_risk`).

### 5. News
Up to 8 items from `headlines`: 🟢/🔴/⚪ for sentiment, title as a link, source. If empty, say no recent headlines were found.

### 6. Risks and what would change the call
Three or four bullets built from the negative reasons and the levels: which price breaks the stop, which signals flipping would push the score across 5 or 0. Flag clearly: leveraged ETFs, unprofitable companies, high volatility, thin analyst coverage.

### 7. Footer
One line: "Rule-based signals from price data, fundamentals, analyst data and headline keywords. Not financial advice; do your own research before you trade." Nothing after it.

## Rules
- Plain language. Explain each term the first time it appears (ATR, RSI, MACD, P/E, PEG, golden cross, reward-to-risk).
- The call is `call.call`. Do not upgrade or soften it with your own opinion; if the user pushes back, explain which reasons drive it.
- Never repeat share counts, cash or account details from `portfolio.json`; only the cost per share and % gain/loss.
