"""Stock analysis engine: technicals, candlestick patterns, fundamentals,
analyst consensus and news sentiment, combined into a scored signal with
human-readable reasons.

This is a rule-based research tool, not financial advice.
"""
from __future__ import annotations

import re
import ssl
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import certifi
import numpy as np
import pandas as pd
import yfinance as yf


@dataclass
class Reason:
    category: str  # Technical | Candles | Fundamental | Analysts | News
    text: str
    points: float  # positive = bullish, negative = bearish


@dataclass
class Analysis:
    ticker: str
    name: str
    price: float
    history: pd.DataFrame
    reasons: list[Reason] = field(default_factory=list)
    headlines: list[dict] = field(default_factory=list)
    atr: float = float("nan")
    error: str | None = None
    meta: dict = field(default_factory=dict)
    levels: dict = field(default_factory=dict)

    def score_by(self, category: str) -> float:
        return sum(r.points for r in self.reasons if r.category == category)

    @property
    def score(self) -> float:
        return round(sum(r.points for r in self.reasons), 1)

    @property
    def verdict(self) -> str:
        s = self.score
        if s >= 9:
            return "Strong bullish"
        if s >= 5:
            return "Bullish"
        if s > -3:
            return "Neutral"
        if s > -6:
            return "Bearish"
        return "Strong bearish"

    @property
    def holding_horizon(self) -> str:
        """Suggest a horizon based on what is driving the signal."""
        short = self.score_by("Technical") + self.score_by("Candles")
        long = self.score_by("Fundamental") + self.score_by("Analysts")
        if self.score < 5:
            return "—"
        if long >= 3 and short >= 2:
            return "3–12 months (fundamentals + momentum agree)"
        if long >= 3:
            return "6–18 months (fundamentals-driven, be patient)"
        if short >= 2:
            return "1–6 weeks (technical/momentum trade, use a stop)"
        return "1–3 months"

    @property
    def short_score(self) -> float:
        """Signals that matter over days to weeks: chart, candles, news flow."""
        return round(self.score_by("Technical") + self.score_by("Candles") + self.score_by("News"), 1)

    @property
    def long_score(self) -> float:
        """Signals that matter over months to years: business quality, valuation, analysts, long trend."""
        trend = 1 if self.levels.get("sma200") and self.price > self.levels["sma200"] else -1
        return round(self.score_by("Fundamental") + self.score_by("Analysts") + trend, 1)

    def holding_verdict(self) -> str:
        s = self.score
        if s >= 5:
            return "STAY — signals support holding / adding"
        if s >= 0:
            return "STAY — no strong reason to exit, keep watching"
        if s > -3:
            return "REVIEW — weakening signals, consider tightening stop"
        return "CONSIDER EXIT — most signals turned negative"


# ---------------------------------------------------------------- indicators

def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + gain / loss)


def macd(close: pd.Series):
    line = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    signal = line.ewm(span=9, adjust=False).mean()
    return line, signal


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev = df["Close"].shift()
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - prev).abs(), (df["Low"] - prev).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


# ------------------------------------------------------- candlestick patterns

def detect_candles(df: pd.DataFrame, lookback: int = 3) -> list[tuple[str, str, int]]:
    """Return (pattern, 'bull'|'bear'|'neutral', days_ago) found in the last `lookback` sessions."""
    o, h, l, c = (df[k].to_numpy() for k in ("Open", "High", "Low", "Close"))
    body = np.abs(c - o)
    rng = h - l
    avg_body = pd.Series(body).rolling(20).mean().to_numpy()
    upper = h - np.maximum(o, c)
    lower = np.minimum(o, c) - l
    sma20 = pd.Series(c).rolling(20).mean().to_numpy()
    found = []
    n = len(df)
    for i in range(n - lookback, n):
        ago = n - 1 - i
        downtrend = c[i - 1] < sma20[i - 1]
        uptrend = c[i - 1] > sma20[i - 1]
        # Engulfing
        if c[i - 1] < o[i - 1] and c[i] > o[i] and o[i] <= c[i - 1] and c[i] >= o[i - 1] and body[i] > body[i - 1]:
            found.append(("Bullish engulfing", "bull", ago))
        if c[i - 1] > o[i - 1] and c[i] < o[i] and o[i] >= c[i - 1] and c[i] <= o[i - 1] and body[i] > body[i - 1]:
            found.append(("Bearish engulfing", "bear", ago))
        # Hammer / hanging man / shooting star / inverted hammer
        if rng[i] > 0 and lower[i] >= 2 * body[i] and upper[i] <= 0.3 * body[i] + 0.05 * rng[i]:
            if downtrend:
                found.append(("Hammer (after decline)", "bull", ago))
            elif uptrend:
                found.append(("Hanging man (after rally)", "bear", ago))
        if rng[i] > 0 and upper[i] >= 2 * body[i] and lower[i] <= 0.3 * body[i] + 0.05 * rng[i]:
            if uptrend:
                found.append(("Shooting star (after rally)", "bear", ago))
            elif downtrend:
                found.append(("Inverted hammer (after decline)", "bull", ago))
        # Doji
        if rng[i] > 0 and body[i] <= 0.1 * rng[i]:
            found.append(("Doji (indecision)", "neutral", ago))
        # Morning / evening star
        if i >= 2:
            small_mid = body[i - 1] < 0.5 * avg_body[i]
            if c[i - 2] < o[i - 2] and body[i - 2] > avg_body[i] and small_mid and c[i] > o[i] and c[i] > (o[i - 2] + c[i - 2]) / 2:
                found.append(("Morning star", "bull", ago))
            if c[i - 2] > o[i - 2] and body[i - 2] > avg_body[i] and small_mid and c[i] < o[i] and c[i] < (o[i - 2] + c[i - 2]) / 2:
                found.append(("Evening star", "bear", ago))
            # Three white soldiers / black crows
            if all(c[j] > o[j] and body[j] > 0.6 * avg_body[i] for j in (i - 2, i - 1, i)) and c[i] > c[i - 1] > c[i - 2]:
                found.append(("Three white soldiers", "bull", ago))
            if all(c[j] < o[j] and body[j] > 0.6 * avg_body[i] for j in (i - 2, i - 1, i)) and c[i] < c[i - 1] < c[i - 2]:
                found.append(("Three black crows", "bear", ago))
    # keep only the most recent occurrence of each pattern
    latest = {}
    for name, kind, ago in found:
        if name not in latest or ago < latest[name][2]:
            latest[name] = (name, kind, ago)
    return list(latest.values())


# -------------------------------------------------------------- news / media

POSITIVE = r"beat|beats|surge|soar|jump|rall(y|ies)|upgrade|record|raise[sd]? (guidance|outlook)|strong|outperform|buy rating|tops|growth|breakthrough|wins|approval|bullish|partnership"
NEGATIVE = r"miss|misses|plunge|sink|tumble|slump|downgrade|cut[s]? (guidance|outlook)|weak|lawsuit|probe|investigation|recall|underperform|sell rating|warn|layoff|fraud|bearish|falls|drops|slides|antitrust|fine[sd]?"


def fetch_news_query(query: str, days: int = 7, limit: int = 12) -> list[dict]:
    q = urllib.parse.quote(f"{query} when:{days}d")
    url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        ctx = ssl.create_default_context(cafile=certifi.where())
        root = ET.fromstring(urllib.request.urlopen(req, timeout=10, context=ctx).read())
    except Exception:
        return []
    out = []
    for item in root.iter("item"):
        title = item.findtext("title") or ""
        source = item.findtext("source") or ""
        pos = len(re.findall(POSITIVE, title, re.I))
        neg = len(re.findall(NEGATIVE, title, re.I))
        out.append({
            "title": title.rsplit(" - ", 1)[0],
            "source": source,
            "link": item.findtext("link"),
            "date": item.findtext("pubDate"),
            "sentiment": "positive" if pos > neg else "negative" if neg > pos else "neutral",
        })
        if len(out) >= limit:
            break
    return out


def fetch_news(ticker: str, name: str, days: int = 7, limit: int = 12) -> list[dict]:
    short = re.sub(r",?\s+(Inc\.?|Corporation|Corp\.?|Company|Co\.|Ltd\.?|plc|Holdings|Group)\b.*$", "", name or ticker)
    return fetch_news_query(f'"{short}" stock', days, limit)


# ---------------------------------------------------------------- main entry

def analyze(ticker: str, with_news: bool = True) -> Analysis:
    ticker = ticker.upper().strip()
    t = yf.Ticker(ticker)
    df = t.history(period="2y", auto_adjust=False)
    if df.empty or len(df) < 210:
        return Analysis(ticker, ticker, float("nan"), df, error="Not enough price history")
    try:
        info = t.info or {}
    except Exception:
        info = {}
    close = df["Close"]
    price = float(close.iloc[-1])
    a = Analysis(ticker, info.get("longName") or info.get("shortName") or ticker, price, df)
    R = a.reasons.append
    a.meta = {k: info.get(k) for k in ("sector", "industry", "marketCap", "trailingPE", "forwardPE",
                                       "targetMeanPrice", "targetHighPrice", "targetLowPrice",
                                       "numberOfAnalystOpinions", "dividendYield", "beta")}

    # --- Technical trend & momentum
    sma50, sma200 = close.rolling(50).mean(), close.rolling(200).mean()
    if price > sma50.iloc[-1] > sma200.iloc[-1]:
        R(Reason("Technical", f"Uptrend: price ${price:.2f} above 50-day (${sma50.iloc[-1]:.2f}) and 200-day (${sma200.iloc[-1]:.2f}) averages", 2))
    elif price < sma50.iloc[-1] < sma200.iloc[-1]:
        R(Reason("Technical", f"Downtrend: price below 50-day (${sma50.iloc[-1]:.2f}) and 200-day (${sma200.iloc[-1]:.2f}) averages", -2))
    elif price > sma200.iloc[-1]:
        R(Reason("Technical", "Price above 200-day average (long-term trend intact) but 50-day is mixed", 0.5))
    else:
        R(Reason("Technical", "Price below 200-day average (long-term trend weak)", -1))

    cross = np.sign(sma50 - sma200).diff().iloc[-20:]
    if (cross > 0).any():
        R(Reason("Technical", "Golden cross in the last 20 sessions (50-day crossed above 200-day)", 1.5))
    if (cross < 0).any():
        R(Reason("Technical", "Death cross in the last 20 sessions (50-day crossed below 200-day)", -1.5))

    r = float(rsi(close).iloc[-1])
    if r < 30:
        R(Reason("Technical", f"RSI {r:.0f}: oversold, a rebound is statistically more likely", 1))
    elif r > 70:
        R(Reason("Technical", f"RSI {r:.0f}: overbought, pullback risk is elevated", -1))
    else:
        R(Reason("Technical", f"RSI {r:.0f}: neutral momentum", 0))

    m, s = macd(close)
    if m.iloc[-1] > s.iloc[-1] and (m.iloc[-6:-1] <= s.iloc[-6:-1]).any():
        R(Reason("Technical", "MACD bullish crossover in the last 5 sessions", 1))
    elif m.iloc[-1] < s.iloc[-1] and (m.iloc[-6:-1] >= s.iloc[-6:-1]).any():
        R(Reason("Technical", "MACD bearish crossover in the last 5 sessions", -1))

    hi52, lo52 = close.iloc[-252:].max(), close.iloc[-252:].min()
    pos = (price - lo52) / (hi52 - lo52) if hi52 > lo52 else 0.5
    if price >= 0.97 * hi52:
        R(Reason("Technical", f"Trading near 52-week high (${hi52:.2f}), showing strong relative strength", 0.5))
    elif pos < 0.15:
        R(Reason("Technical", f"Trading near 52-week low (${lo52:.2f})", -0.5))

    vol_ratio = df["Volume"].iloc[-5:].mean() / df["Volume"].iloc[-50:].mean()
    chg5 = price / close.iloc[-6] - 1
    if vol_ratio > 1.5:
        R(Reason("Technical", f"Volume {vol_ratio:.1f}x normal over 5 days while price moved {chg5:+.1%}, so the move has conviction", 0.5 if chg5 > 0 else -0.5))

    a.atr = float(atr(df).iloc[-1])
    rets = np.log(close).diff().iloc[-252:]
    a.levels = {
        "atr": a.atr,
        "vol": float(rets.std() * np.sqrt(252)),  # annualized volatility
        "sma50": float(sma50.iloc[-1]), "sma200": float(sma200.iloc[-1]),
        "high52": float(hi52), "low52": float(lo52),
        "swing_low20": float(df["Low"].iloc[-20:].min()), "high20": float(df["High"].iloc[-20:].max()),
        "max_drawdown": float((close.iloc[-252:] / close.iloc[-252:].cummax() - 1).min()),
    }

    # --- Candlestick patterns
    for name, kind, ago in detect_candles(df):
        when = "today" if ago == 0 else f"{ago} session{'s' if ago > 1 else ''} ago"
        pts = {"bull": 1, "bear": -1, "neutral": 0}[kind]
        R(Reason("Candles", f"{name} ({when})", pts))

    # --- Leveraged / inverse daily ETFs lose value in choppy markets (volatility decay)
    if re.search(r"\b[23]x\b|leverag|ultra(pro)?\b|daily (bull|bear)", a.name, re.I):
        R(Reason("Fundamental", "Leveraged daily ETF: loses value over time when prices swing (volatility decay); "
                                "built for short holds, not buy-and-hold", -1.5))

    # --- Fundamentals
    pe, fpe = info.get("trailingPE"), info.get("forwardPE")
    peg = info.get("trailingPegRatio") or info.get("pegRatio")
    if pe and fpe and pe > 0 and fpe > 0:
        if fpe < pe * 0.85:
            R(Reason("Fundamental", f"Forward P/E {fpe:.1f} well below trailing {pe:.1f}: earnings expected to grow", 1))
        if fpe < 15:
            R(Reason("Fundamental", f"Forward P/E {fpe:.1f}: inexpensive valuation", 1))
        elif fpe > 40:
            R(Reason("Fundamental", f"Forward P/E {fpe:.1f}: expensive, priced for perfection", -1))
    elif pe is None and info.get("trailingEps", 0) and info.get("trailingEps", 0) < 0:
        R(Reason("Fundamental", "Company is not profitable (negative earnings)", -1))
    if peg:
        if 0 < peg < 1:
            R(Reason("Fundamental", f"PEG {peg:.2f} < 1: cheap relative to growth", 1.5))
        elif peg > 3:
            R(Reason("Fundamental", f"PEG {peg:.2f}: valuation high relative to growth", -1))
    rg, eg = info.get("revenueGrowth"), info.get("earningsGrowth")
    if rg is not None:
        if rg > 0.15:
            R(Reason("Fundamental", f"Revenue growing {rg:.0%} year over year", 1))
        elif rg < 0:
            R(Reason("Fundamental", f"Revenue shrinking {rg:.0%} year over year", -1))
    if eg is not None and eg > 0.2:
        R(Reason("Fundamental", f"Earnings growing {eg:.0%} year over year", 0.5))
    elif eg is not None and eg < -0.1:
        R(Reason("Fundamental", f"Earnings declining {eg:.0%} year over year", -0.5))
    roe, pm = info.get("returnOnEquity"), info.get("profitMargins")
    if roe and roe > 0.2:
        R(Reason("Fundamental", f"High return on equity ({roe:.0%}): efficient, quality business", 0.5))
    if pm and pm > 0.2:
        R(Reason("Fundamental", f"Strong profit margin ({pm:.0%})", 0.5))
    de = info.get("debtToEquity")
    if de is not None and de > 200 and info.get("sector") not in ("Financial Services", "Utilities", "Real Estate"):
        R(Reason("Fundamental", f"High debt/equity ({de:.0f}%)", -1))
    fcf = info.get("freeCashflow")
    if fcf is not None and fcf < 0:
        R(Reason("Fundamental", "Negative free cash flow (burning cash)", -0.5))

    # --- Analyst consensus (professional opinion)
    target, n_an = info.get("targetMeanPrice"), info.get("numberOfAnalystOpinions") or 0
    rec = info.get("recommendationKey")
    if target and n_an >= 5:
        up = target / price - 1
        pts = 1.5 if up > 0.2 else 0.5 if up > 0.08 else -1 if up < -0.05 else 0
        R(Reason("Analysts", f"{n_an} analysts' mean target ${target:.2f} ({up:+.0%} vs current price)", pts))
    if rec and n_an >= 5:
        pts = {"strong_buy": 1, "buy": 0.5, "hold": 0, "underperform": -1, "sell": -1.5}.get(rec, 0)
        R(Reason("Analysts", f"Consensus rating: {rec.replace('_', ' ').title()}", pts))
    try:
        ud = t.upgrades_downgrades
        if ud is not None and not ud.empty:
            cutoff = datetime.now() - timedelta(days=30)
            recent = ud[ud.index.tz_localize(None) >= cutoff] if ud.index.tz is not None else ud[ud.index >= cutoff]
            ups = recent[recent["Action"].str.lower() == "up"]
            downs = recent[recent["Action"].str.lower() == "down"]
            if len(ups):
                R(Reason("Analysts", f"Upgraded in last 30 days by: {', '.join(ups['Firm'].head(4))}", min(1.5, 0.5 * len(ups))))
            if len(downs):
                R(Reason("Analysts", f"Downgraded in last 30 days by: {', '.join(downs['Firm'].head(4))}", -min(1.5, 0.5 * len(downs))))
    except Exception:
        pass

    # --- News sentiment
    if with_news:
        a.headlines = fetch_news(ticker, a.name)
        p = sum(h["sentiment"] == "positive" for h in a.headlines)
        n = sum(h["sentiment"] == "negative" for h in a.headlines)
        if a.headlines:
            net = p - n
            pts = 1 if net >= 3 else 0.5 if net >= 1 else -1 if net <= -3 else -0.5 if net <= -1 else 0
            R(Reason("News", f"Last 7 days: {p} positive / {n} negative / {len(a.headlines) - p - n} neutral headlines", pts))

    return a


UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "AVGO", "TSM", "AMD", "ORCL", "CRM", "ADBE", "NFLX",
    "JPM", "V", "MA", "BAC", "GS", "BRK-B", "LLY", "UNH", "JNJ", "ABBV", "MRK", "NVO",
    "COST", "WMT", "PG", "KO", "PEP", "MCD", "NKE", "HD",
    "XOM", "CVX", "CAT", "GE", "LMT", "UBER", "PLTR", "TSLA", "SHOP", "PYPL", "INTC",
    # higher-risk growth
    "COIN", "MSTR", "HOOD", "SOFI", "AFRM", "RKLB", "IONQ", "SMCI", "MU", "ARM", "APP", "CRWD", "NET",
    "DDOG", "SNOW", "RBLX", "RIVN",
    # lower-risk defensives
    "VZ", "T", "DUK", "SO", "NEE", "LIN", "UNP", "CL", "MDLZ", "PM", "TXN", "HON", "ADP",
]


def scan(tickers=UNIVERSE, with_news=False) -> list[Analysis]:
    results = []
    for tk in tickers:
        try:
            a = analyze(tk, with_news=with_news)
            if not a.error:
                results.append(a)
        except Exception as e:  # keep scanning if one ticker fails
            print(f"skip {tk}: {e}")
    return sorted(results, key=lambda a: a.score, reverse=True)
