---
name: analyze
description: "Full report on one stock or ETF: score, every reason behind it, whether the price is good, trade levels with expected time to each target, and a buy / wait / avoid call. Use for /analyze TICKER [COST], 'analyze X', 'check X', or 'should I buy X'."
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
- **Earnings:** if `earnings` is not null, add "Next earnings: `earnings.date` (in `earnings.days` days)". If `earnings.within_week` is true, start this line with ⚠️ and add that the stock can move sharply in either direction on the report, so a new position now carries extra risk. If `earnings` is null, say the next earnings date wasn't available.

### 2. Is this a good price?
From `price_check`:
- **`label`** in bold.
- Two short tables, **Value** (`price_check.value`: is the business cheap or expensive) and **Timing** (`price_check.timing`: is today a good moment to buy), each row with 🟢/🔴/⚪ by points, the text, and the points. Give each table's total (`value_points`, `timing_points`).
- If `better_entry` is not null: "A calmer entry would be around $`better_entry.price` (`better_entry.pct` from here), `better_entry.why`." Make clear this is a level to watch, not a prediction that it will get there.
- If `held` is true, frame it as "would you buy more here", not as a reason to sell.

### 3. Snapshot
A small table: name, price and `as_of` date, sector / industry, market cap (in $B), trailing and forward P/E, beta, dividend yield, 52-week high and low with distance from each, annual volatility (`levels.vol`), and the worst drop in the last year (`levels.max_drawdown`). Leave out rows whose value is null.

### 4. Why: the reasons
One table per category that has reasons, in this order: Technical, Candles, Fundamental, Analysts, News. Columns: signal (🟢 positive points, 🔴 negative, ⚪ zero), reason, points. Under each table: the category total from `score_by_category` and one plain sentence on what it means. Then the split: `short_score` (days to weeks: chart, candles, news) vs `long_score` (months to years: business, analysts, 200-day trend), and whether they agree.

### 5. Trade levels and expected time to take profit
- If held: `position.plan`: stop-loss, take-profit 1 and 2 (price and % from now), and its notes.
- If not held: both plans side by side: `short_trade` and `long_position` (entry, stop, target, reward-to-risk, hold time and the reason for it). Say whether the stock was treated as high-risk (`high_risk`).
- **Expected time** for every target, from its `*_time` field (`target_time`, `tp1_time`, `tp2_time`), as a row or column next to the target:
  - **Typical time:** `typical`, with the middle range `range_text` (half of the simulated runs that hit the target got there within that range).
  - **Chance of reaching it before the stop:** `p_target_first` as a percent.
  - If `typical` is null: "Rarely reached before the stop in simulations; no reliable time estimate."
  - If `earnings_first` is true, mark that target with ⚠️ and note that the earnings report comes before its typical time, so the estimate is less reliable (the simulation can't predict an earnings jump or drop).
- After the table, one line on the method: estimates come from `take_profit_timing.method`; say the trend used was `annual_drift_used` per year. Add: "These are rough odds from the stock's own history, not a forecast; earnings, news or a market drop can change them fast."
- If a typical time is much longer than the plan's `hold` period, point that out (the target may not fit that holding style).

### 6. News
Up to 8 items from `headlines`: 🟢/🔴/⚪ for sentiment, title as a link, source. If empty, say no recent headlines were found.

### 7. Risks and what would change the call
Three or four bullets built from the negative reasons and the levels: which price breaks the stop, which signals flipping would push the score across 5 or 0. Flag clearly: leveraged ETFs, unprofitable companies, high volatility, thin analyst coverage, and an earnings report within the next month.

### 8. Footer
One line: "Rule-based signals from price data, fundamentals, analyst data and headline keywords. Not financial advice; do your own research before you trade." Nothing after it.

## Rules
- Plain language. Explain each term the first time it appears (ATR, RSI, MACD, P/E, PEG, golden cross, reward-to-risk).
- Never present a time estimate or a better-entry price as a promise. They are odds and reference levels.
- The call is `call.call`. Do not upgrade or soften it with your own opinion; if the user pushes back, explain which reasons drive it.
- Never repeat share counts, cash or account details from `portfolio.json`; only the cost per share and % gain/loss.
