# Stock Analyzer: an `/analyze` skill for Claude Code

Type `/analyze NVDA` in Claude Code and get a full research report on any stock or ETF:

1. **The call**: BUY SIGNAL, WAIT / WATCHLIST, or AVOID FOR NOW, with the score behind it
2. **Is this a good price?** Value (is the business cheap or expensive) and timing (is today a good moment, or has it run up), with a calmer entry level when it's stretched
3. **Snapshot**: price, valuation, 52-week range, volatility, worst drop in the last year
4. **Why**: every signal that moved the score, grouped into technical, candlestick, fundamental, analyst and news reasons, each with its points
5. **Trade levels**: entry, stop-loss and target for a short trade (days to weeks) and a long hold (months), with the **expected time to reach each target**, the chance of hitting it before the stop, and a warning when earnings come first
6. **News**: last week's headlines, marked positive or negative
7. **Risks**: what would flip the call

Already own it? Add your purchase price, `/analyze IREN 62.20`, and you get a stay / review / exit call with stop-loss and two take-profit levels instead.

> ⚠️ **Not financial advice.** This is a rule-based research tool built as a learning project. The signals come from fixed rules applied to public data (Yahoo Finance, Google News); they can be wrong, late, or based on incomplete data, and past price patterns do not predict the future. Check everything yourself before you trade.

## Install

You need [Claude Code](https://claude.com/claude-code) and Python 3.10 or newer.

```bash
git clone https://github.com/orenball/stock-analyzer.git
cd stock-analyzer
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt        # Windows: .venv\Scripts\pip install -r requirements.txt
```

Then open Claude Code in this folder. The skill lives in `.claude/skills/analyze/`, so Claude Code picks it up automatically.

**Use it in other projects too:** copy `.claude/skills/analyze/` into `~/.claude/skills/` and change the run command in its `SKILL.md` to the full path of this folder's `engine/report.py`.

## Usage

| You type | You get |
|---|---|
| `/analyze AAPL` | Full report, judged as a new buy |
| `/analyze IREN 62.20` | Full report as a holding bought at $62.20: stay / exit call and your stop / take-profit levels |
| `should I buy TSLA?` | Same as `/analyze TSLA` |
| `/analyze TEVA.TA` | Non-US stocks with a Yahoo market suffix (`.TA` Tel Aviv, `.L` London, `.DE` Frankfurt, `.T` Tokyo) |

You can also run the engine without Claude and read the raw JSON:

```bash
.venv/bin/python engine/report.py NVDA
```

### Optional: your portfolio

To skip typing your cost each time, copy `portfolio.example.json` to `portfolio.json` and fill in your positions. Any ticker found there is analyzed as a holding. `portfolio.json` is in `.gitignore`, so it never gets uploaded.

## How the score works

Each rule adds or subtracts points; the total is the score.

| Category | Examples of what it checks |
|---|---|
| Technical | Price vs 50- and 200-day averages, golden / death cross, RSI, MACD crossovers, 52-week high / low, unusual volume |
| Candles | Recent candlestick reversal patterns (engulfing, hammer, morning / evening star…) |
| Fundamental | P/E and forward P/E, PEG, revenue and earnings growth, margins, return on equity, debt, free cash flow, leveraged-ETF decay |
| Analysts | Mean price target vs current price, consensus rating, upgrades / downgrades in the last 30 days |
| News | Positive vs negative keywords in the last 7 days of headlines |

| Score | Signal | Call (not owned) |
|---|---|---|
| 9 or more | Strong bullish | BUY SIGNAL |
| 5 to 9 | Bullish | BUY SIGNAL (short-term only if the long-term signals are negative) |
| 0 to 5 | Neutral | WAIT / WATCHLIST |
| below 0 | Bearish / strong bearish | AVOID FOR NOW |

Stop-loss and targets come from the stock's average daily range (ATR), recent swing lows, the 200-day average, the 52-week high and analyst targets. See `engine/plans.py`.

### Is this a good price?

Two separate questions, each with its own points (`engine/timing.py`):

| Value: is the business cheap? | Timing: is today a good moment? |
|---|---|
| Forward P/E: < 15 cheap (+1), 15–30 normal (0), 30–45 rich (−0.5), > 45 very expensive (−1) | RSI: < 35 oversold (+1), 62–70 getting hot (−0.5), > 70 overbought (−1) |
| PEG: < 1 cheap (+1), 1–2 fair (0), 2–3 pricey (−0.5), > 3 expensive (−1) | Distance above the 200-day average: 0–15% healthy (+0.5), 15–30% (−0.5), > 30% (−1) |
| Analyst average target: > 20% upside (+1), 8–20% (+0.5), more than 5% below the price (−1) | Top 10% of the 52-week range (−0.5) |

Value ≥ 1 and timing ≥ 0 → **good price**. Value ≥ 1 but timing below 0 → **good value, stretched entry**, with the 50-day average shown as a calmer entry level. Value ≤ −1 → **expensive**. Anything else → **fair price**.

### Expected time to take profit

For each target, the engine builds 3,000 simulated two-year price paths by reshuffling the stock's real daily moves from the last year. That keeps its true volatility and its sudden jumps. Last year's trend is counted at half strength and capped at ±30% a year, so one hot year doesn't promise another. For each target you get:

- the **typical time** to reach it (median) and the middle range,
- the **chance it's reached before the stop**.

These are odds based on how the stock has moved, not a forecast. Earnings, news or a market crash can change them quickly.

### Earnings warning

The report shows the next earnings date from Yahoo Finance. A ⚠️ appears when earnings are less than a week away, and on any target whose typical time runs past the earnings report, because a single earnings day can move the stock more than weeks of normal trading.

## Files

```
.claude/skills/analyze/SKILL.md   the skill: how Claude runs the engine and writes the report
engine/analysis.py                scoring rules, indicators, candlesticks, news
engine/plans.py                   stop-loss and take-profit levels
engine/timing.py                  time to each target, and the price check
engine/report.py                  runs one ticker, prints JSON
portfolio.example.json            format for the optional portfolio file
```

## License

MIT, see [LICENSE](LICENSE).
