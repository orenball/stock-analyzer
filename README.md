# Stock Analyzer: an `/analyze` skill for Claude Code

Type `/analyze NVDA` in Claude Code and get a full research report on any stock or ETF:

1. **The call**: BUY SIGNAL, WAIT / WATCHLIST, or AVOID FOR NOW, with the score behind it
2. **Snapshot**: price, valuation, 52-week range, volatility, worst drop in the last year
3. **Why**: every signal that moved the score, grouped into technical, candlestick, fundamental, analyst and news reasons, each with its points
4. **Trade levels**: entry, stop-loss and target for a short trade (days to weeks) and a long hold (months)
5. **News**: last week's headlines, marked positive or negative
6. **Risks**: what would flip the call

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

## Files

```
.claude/skills/analyze/SKILL.md   the skill: how Claude runs the engine and writes the report
engine/analysis.py                scoring rules, indicators, candlesticks, news
engine/plans.py                   stop-loss and take-profit levels
engine/report.py                  runs one ticker, prints JSON
portfolio.example.json            format for the optional portfolio file
```

## License

MIT, see [LICENSE](LICENSE).
