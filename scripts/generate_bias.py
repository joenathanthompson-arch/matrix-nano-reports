#!/usr/bin/env python3
"""
Matrix Nano Bias Generation Script
Fetches live market data, analyzes conditions via LLM, and commits
JSON bias scores + Markdown executive summary to GitHub.

Schedule: 2:30 AM ET and 5:30 PM ET, Sunday through Friday
"""

import os
import sys
import json
import subprocess
import traceback
from datetime import datetime, timedelta
import pytz
import yfinance as yf
import requests

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ET_TZ = pytz.timezone("America/New_York")

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
FRED_API_KEY = "abcdef"  # FRED does not require a key for public series via direct URL

# Yahoo Finance symbols
YF_SYMBOLS = {
    "vix":     "^VIX",
    "sp500":   "^GSPC",
    "nasdaq":  "^NDX",
    "dow":     "^DJI",
    "russell": "^RUT",
    "sox":     "^SOX",
    "dxy":     "DX-Y.NYB",
    "gold":    "GC=F",
    "silver":  "SI=F",
    "crude":   "CL=F",
    "natgas":  "NG=F",
    "eurusd":  "EURUSD=X",
    "audusd":  "AUDUSD=X",
    "usdjpy":  "USDJPY=X",
    "gbpusd":  "GBPUSD=X",
    "tnx":     "^TNX",
    "btc":     "BTC-USD",
}

# FRED series (no API key needed for recent observations via FRED API)
FRED_SERIES = {
    "real_yield_10y": "DFII10",
    "hy_spread":      "BAMLH0A0HYM2",
    "fedfunds":       "FEDFUNDS",
    "dgs2":           "DGS2",
    "dgs10":          "DGS10",
    "breakeven_10y":  "T10YIE",
}


# ─────────────────────────────────────────────
# DATA FETCHING
# ─────────────────────────────────────────────

def fetch_yfinance_data():
    """Fetch latest price data from Yahoo Finance for all tracked symbols."""
    data = {}
    stale = []
    symbols_list = list(YF_SYMBOLS.values())
    try:
        tickers = yf.download(
            symbols_list,
            period="10d",
            interval="1d",
            progress=False,
            auto_adjust=True,
            group_by="ticker",
        )
        for key, sym in YF_SYMBOLS.items():
            try:
                if sym in tickers.columns.get_level_values(0):
                    closes = tickers[sym]["Close"].dropna()
                else:
                    closes = tickers["Close"][sym].dropna() if "Close" in tickers.columns else None

                if closes is None or len(closes) == 0:
                    raise ValueError("No data")

                current = float(closes.iloc[-1])
                prev = float(closes.iloc[-2]) if len(closes) >= 2 else current
                change_pct = ((current - prev) / prev * 100) if prev != 0 else 0.0
                change_5d = float(closes.iloc[-1] - closes.iloc[0]) if len(closes) >= 5 else 0.0
                trend_5d = "rising" if change_5d > 0 else ("falling" if change_5d < 0 else "stable")

                data[key] = {
                    "value": round(current, 4),
                    "change_1d_pct": round(change_pct, 2),
                    "change_5d": round(change_5d, 4),
                    "trend": trend_5d,
                }
            except Exception as e:
                data[key] = {"value": None, "error": str(e)}
                stale.append(sym)
    except Exception as e:
        print(f"[WARN] yfinance batch download failed: {e}")
        # Fallback: fetch individually
        for key, sym in YF_SYMBOLS.items():
            try:
                t = yf.Ticker(sym)
                hist = t.history(period="10d")
                if hist.empty:
                    raise ValueError("Empty history")
                current = float(hist["Close"].iloc[-1])
                prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else current
                change_pct = ((current - prev) / prev * 100) if prev != 0 else 0.0
                change_5d = float(hist["Close"].iloc[-1] - hist["Close"].iloc[0]) if len(hist) >= 5 else 0.0
                trend_5d = "rising" if change_5d > 0 else ("falling" if change_5d < 0 else "stable")
                data[key] = {
                    "value": round(current, 4),
                    "change_1d_pct": round(change_pct, 2),
                    "change_5d": round(change_5d, 4),
                    "trend": trend_5d,
                }
            except Exception as e2:
                data[key] = {"value": None, "error": str(e2)}
                stale.append(sym)

    return data, stale


def fetch_fred_series(series_id):
    """Fetch the most recent value for a FRED series (no API key required for public data)."""
    try:
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        lines = resp.text.strip().split("\n")
        # Last non-empty line with a valid value
        for line in reversed(lines[1:]):
            parts = line.strip().split(",")
            if len(parts) == 2 and parts[1] not in (".", ""):
                return float(parts[1])
        return None
    except Exception as e:
        print(f"[WARN] FRED fetch failed for {series_id}: {e}")
        return None


def fetch_fred_data():
    """Fetch all FRED economic series."""
    data = {}
    stale = []
    for key, series_id in FRED_SERIES.items():
        val = fetch_fred_series(series_id)
        if val is not None:
            data[key] = val
        else:
            data[key] = None
            stale.append(series_id)
    return data, stale


def fetch_economic_calendar():
    """
    Check ForexFactory for high-impact events today and this week.
    Returns a simple dict with flags and event names.
    """
    now_et = datetime.now(ET_TZ)
    today_str = now_et.strftime("%Y-%m-%d")

    # Known recurring high-impact events (approximate detection by date)
    # We use a simple heuristic: check if today is first Friday (NFP)
    high_impact_today = False
    high_impact_events = []
    in_blackout = False

    # First Friday of month = NFP
    first_friday = None
    for day in range(1, 8):
        d = datetime(now_et.year, now_et.month, day, tzinfo=ET_TZ)
        if d.weekday() == 4:  # Friday
            first_friday = d
            break
    if first_friday and now_et.date() == first_friday.date():
        high_impact_today = True
        high_impact_events.append("NFP")

    # Try to scrape ForexFactory for today's events
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get("https://nfs.faireconomy.media/ff_calendar_thisweek.json", timeout=10)
        if resp.status_code == 200:
            events = resp.json()
            for event in events:
                impact = event.get("impact", "").upper()
                title = event.get("title", "")
                date_str = event.get("date", "")
                if impact == "HIGH" and today_str in date_str:
                    high_impact_today = True
                    high_impact_events.append(title)
    except Exception as e:
        print(f"[WARN] ForexFactory calendar fetch failed: {e}")

    # Deduplicate
    high_impact_events = list(set(high_impact_events))

    # Determine FOMC and NFP days away (rough estimate)
    fomc_days_away = 99
    nfp_days_away = 99
    if first_friday:
        delta = (first_friday.date() - now_et.date()).days
        nfp_days_away = delta if delta >= 0 else delta + 30  # approx next month

    return {
        "high_impact_today": high_impact_today,
        "high_impact_events": high_impact_events,
        "fomc_days_away": fomc_days_away,
        "nfp_days_away": nfp_days_away,
        "in_blackout": in_blackout,
    }


# ─────────────────────────────────────────────
# LLM ANALYSIS
# ─────────────────────────────────────────────

def build_analysis_prompt(market_data, fred_data, calendar, run_type, now_et):
    """Build the prompt for the LLM with all live data injected."""

    def v(d, key, fmt=".2f"):
        val = d.get(key, {})
        if isinstance(val, dict):
            value = val.get("value")
            trend = val.get("trend", "")
            chg = val.get("change_1d_pct")
            if value is None:
                return "N/A"
            chg_str = f" ({chg:+.2f}% 1d)" if chg is not None else ""
            return f"{value:{fmt}}{chg_str} [{trend}]"
        elif val is None:
            return "N/A"
        else:
            return f"{val:{fmt}}"

    prompt = f"""You are the AI Bias Advisor for Matrix Nano, a futures trading system.

## CURRENT DATE/TIME
{now_et.strftime('%Y-%m-%d %H:%M')} ET | Run Type: {run_type}

## LIVE MARKET DATA (just fetched)

### Equity Indices
- S&P 500 (^GSPC): {v(market_data, 'sp500')}
- NASDAQ 100 (^NDX): {v(market_data, 'nasdaq')}
- Dow Jones (^DJI): {v(market_data, 'dow')}
- Russell 2000 (^RUT): {v(market_data, 'russell')}
- SOX Semiconductors (^SOX): {v(market_data, 'sox')}

### Volatility & Risk
- VIX: {v(market_data, 'vix')}

### USD & FX
- DXY Dollar Index: {v(market_data, 'dxy')}
- EUR/USD: {v(market_data, 'eurusd')}
- AUD/USD: {v(market_data, 'audusd')}
- USD/JPY: {v(market_data, 'usdjpy')}
- GBP/USD: {v(market_data, 'gbpusd')}

### Commodities
- Gold (GC=F): {v(market_data, 'gold')}
- Silver (SI=F): {v(market_data, 'silver')}
- Crude Oil (CL=F): {v(market_data, 'crude')}
- Natural Gas (NG=F): {v(market_data, 'natgas')}

### Fixed Income
- 10Y Treasury Yield (^TNX): {v(market_data, 'tnx')}%

### Crypto
- Bitcoin (BTC-USD): {v(market_data, 'btc')}

### FRED Economic Data
- Fed Funds Rate: {fred_data.get('fedfunds', 'N/A')}%
- 10Y Real Yield (TIPS): {fred_data.get('real_yield_10y', 'N/A')}%
- HY Credit Spread: {fred_data.get('hy_spread', 'N/A')} bps
- 2Y Treasury: {fred_data.get('dgs2', 'N/A')}%
- 10Y Treasury: {fred_data.get('dgs10', 'N/A')}%
- 10Y Breakeven Inflation: {fred_data.get('breakeven_10y', 'N/A')}%

### Economic Calendar
- High-impact events today: {calendar['high_impact_today']}
- Events: {', '.join(calendar['high_impact_events']) if calendar['high_impact_events'] else 'None'}
- FOMC days away: {calendar['fomc_days_away']}
- NFP days away: {calendar['nfp_days_away']}
- In blackout window: {calendar['in_blackout']}

---

## YOUR TASK

Analyze the above data and generate bias scores for Matrix Nano.

### SCORING RULES
- Scores: integers from -5 to +5 ONLY (no decimals)
- Signal mapping:
  - -5 to -4: STRONG_BEARISH
  - -3 to -2: BEARISH
  - -1: SLIGHT_BEARISH
  - 0: NEUTRAL
  - +1: SLIGHT_BULLISH
  - +2 to +3: BULLISH
  - +4 to +5: STRONG_BULLISH
- Confidence: integers 1-10
- Provide BOTH intraday (hours to EOD) and swing (1-5 days) scores
- Reasons must be under 100 characters

### NEWS IMPACT RULES
- FOMC day: Set ALL scores to 0, confidence to 3
- NFP day: Reduce all confidence by 3
- CPI/PPI day: Reduce all confidence by 2
- In blackout: Note in output

### RUN TYPE CONTEXT
{"- PRE (2:30 AM): Weight Asia/Europe session data more heavily. Focus on overnight positioning." if run_type == "PRE" else "- EOD (5:30 PM): Capture full US session sentiment. Note after-hours developments."}

### ASSET CLASSES TO SCORE
1. OVERALL - General risk-on/risk-off market sentiment
2. EQUITY_INDEX - ES, NQ, YM, RTY, MES, MNQ, MYM, M2K
3. FIXED_INCOME - ZB, ZN, ZT, ZF (inverse: bearish = rates rising)
4. ENERGY - CL, NG, RB, HO, MCL
5. METALS - GC, SI, HG, MGC
6. AGRICULTURE - ZC, ZS, ZW, ZM, ZL (grain/soft commodities)
7. FX - 6E, 6A, 6J, 6B, M6E (positive = bearish USD / bullish non-USD)
8. CRYPTO - BTC, ETH, MBT
9. VOLATILITY - VX, VXM (negative = low vol / sell premium environment)

---

## OUTPUT FORMAT

Respond with ONLY a valid JSON object. No markdown, no explanation, no code blocks.
The JSON must follow this EXACT structure:

{{
  "overall": {{
    "intraday": {{"score": INT, "signal": "STRING", "confidence": INT, "reason": "STRING"}},
    "swing": {{"score": INT, "signal": "STRING", "confidence": INT, "reason": "STRING"}}
  }},
  "asset_classes": {{
    "EQUITY_INDEX": {{
      "intraday": {{"score": INT, "signal": "STRING", "confidence": INT, "reason": "STRING"}},
      "swing": {{"score": INT, "signal": "STRING", "confidence": INT, "reason": "STRING"}}
    }},
    "FIXED_INCOME": {{
      "intraday": {{"score": INT, "signal": "STRING", "confidence": INT, "reason": "STRING"}},
      "swing": {{"score": INT, "signal": "STRING", "confidence": INT, "reason": "STRING"}}
    }},
    "ENERGY": {{
      "intraday": {{"score": INT, "signal": "STRING", "confidence": INT, "reason": "STRING"}},
      "swing": {{"score": INT, "signal": "STRING", "confidence": INT, "reason": "STRING"}}
    }},
    "METALS": {{
      "intraday": {{"score": INT, "signal": "STRING", "confidence": INT, "reason": "STRING"}},
      "swing": {{"score": INT, "signal": "STRING", "confidence": INT, "reason": "STRING"}}
    }},
    "AGRICULTURE": {{
      "intraday": {{"score": INT, "signal": "STRING", "confidence": INT, "reason": "STRING"}},
      "swing": {{"score": INT, "signal": "STRING", "confidence": INT, "reason": "STRING"}}
    }},
    "FX": {{
      "intraday": {{"score": INT, "signal": "STRING", "confidence": INT, "reason": "STRING"}},
      "swing": {{"score": INT, "signal": "STRING", "confidence": INT, "reason": "STRING"}}
    }},
    "CRYPTO": {{
      "intraday": {{"score": INT, "signal": "STRING", "confidence": INT, "reason": "STRING"}},
      "swing": {{"score": INT, "signal": "STRING", "confidence": INT, "reason": "STRING"}}
    }},
    "VOLATILITY": {{
      "intraday": {{"score": INT, "signal": "STRING", "confidence": INT, "reason": "STRING"}},
      "swing": {{"score": INT, "signal": "STRING", "confidence": INT, "reason": "STRING"}}
    }}
  }},
  "key_drivers": ["STRING", "STRING", "STRING"],
  "executive_summary": "STRING (3-4 sentences summarizing overall market conditions and key themes)"
}}
"""
    return prompt


def call_llm(prompt):
    """Call the OpenAI-compatible LLM API."""
    from openai import OpenAI
    client = OpenAI()
    response = client.chat.completions.create(
        model="gemini-2.5-flash",
        messages=[
            {"role": "system", "content": "You are a professional market analyst. Always respond with valid JSON only, no markdown or code blocks."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,
        max_tokens=2000,
    )
    return response.choices[0].message.content.strip()


# ─────────────────────────────────────────────
# VALIDATION
# ─────────────────────────────────────────────

SIGNAL_MAP = {
    -5: "STRONG_BEARISH", -4: "STRONG_BEARISH",
    -3: "BEARISH", -2: "BEARISH",
    -1: "SLIGHT_BEARISH",
    0: "NEUTRAL",
    1: "SLIGHT_BULLISH",
    2: "BULLISH", 3: "BULLISH",
    4: "STRONG_BULLISH", 5: "STRONG_BULLISH",
}


def validate_and_fix(bias_data):
    """Validate and auto-correct bias scores."""
    errors = []

    def fix_entry(entry, path):
        score = entry.get("score")
        if not isinstance(score, int):
            try:
                score = int(round(float(score)))
                entry["score"] = score
            except:
                entry["score"] = 0
                errors.append(f"{path}: invalid score, defaulting to 0")
        score = max(-5, min(5, entry["score"]))
        entry["score"] = score
        expected_signal = SIGNAL_MAP[score]
        if entry.get("signal") != expected_signal:
            entry["signal"] = expected_signal
            errors.append(f"{path}: signal corrected to {expected_signal}")
        conf = entry.get("confidence", 5)
        if not isinstance(conf, int):
            conf = int(round(float(conf)))
        entry["confidence"] = max(1, min(10, conf))
        reason = entry.get("reason", "")
        if len(reason) > 100:
            entry["reason"] = reason[:97] + "..."
        return entry

    # Fix overall
    for tf in ["intraday", "swing"]:
        if tf in bias_data.get("overall", {}):
            bias_data["overall"][tf] = fix_entry(bias_data["overall"][tf], f"overall.{tf}")

    # Fix asset classes
    # Symbols per asset class per v1.2 spec
    ASSET_CLASS_SYMBOLS = {
        "EQUITY_INDEX":  ["ES", "NQ", "YM", "RTY", "MES", "MNQ"],
        "FIXED_INCOME":  ["ZB", "ZN", "ZT", "ZF", "GE", "SR3"],
        "ENERGY":        ["CL", "NG", "RB", "HO", "MCL"],
        "METALS":        ["GC", "SI", "HG", "MGC"],
        "AGRICULTURE":   ["ZC", "ZS", "ZW", "KC", "SB", "CC", "LE", "HE"],
        "FX":            ["6E", "6A", "6J", "6B", "M6E"],
        "CRYPTO":        ["BTC", "ETH", "MBT"],
        "VOLATILITY":    ["VX", "VXM"],
    }
    required_classes = ["EQUITY_INDEX", "FIXED_INCOME", "ENERGY", "METALS", "AGRICULTURE", "FX", "CRYPTO", "VOLATILITY"]
    for ac in required_classes:
        if ac not in bias_data.get("asset_classes", {}):
            bias_data.setdefault("asset_classes", {})[ac] = {
                "symbols": ASSET_CLASS_SYMBOLS.get(ac, []),
                "intraday": {"score": 0, "signal": "NEUTRAL", "confidence": 1, "reason": "Data unavailable - defaulting to neutral"},
                "swing": {"score": 0, "signal": "NEUTRAL", "confidence": 1, "reason": "Data unavailable - defaulting to neutral"},
            }
            errors.append(f"{ac}: missing, defaulted to NEUTRAL")
        else:
            # Ensure symbols field is always present
            if "symbols" not in bias_data["asset_classes"][ac]:
                bias_data["asset_classes"][ac]["symbols"] = ASSET_CLASS_SYMBOLS.get(ac, [])
            for tf in ["intraday", "swing"]:
                if tf in bias_data["asset_classes"][ac]:
                    bias_data["asset_classes"][ac][tf] = fix_entry(
                        bias_data["asset_classes"][ac][tf], f"{ac}.{tf}"
                    )

    return bias_data, errors


# ─────────────────────────────────────────────
# OUTPUT GENERATION
# ─────────────────────────────────────────────

def build_json_output(bias_data, market_data, fred_data, calendar, run_type, now_et, stale_yf, stale_fred, validation_errors):
    """Build the final JSON output matching the required schema."""
    iso_ts = now_et.isoformat()
    run_time_str = now_et.strftime("%H:%M ET")

    vix_val = market_data.get("vix", {}).get("value")
    vix_trend = market_data.get("vix", {}).get("trend", "stable")
    vix_chg = market_data.get("vix", {}).get("change_1d_pct")
    vix_pct_30d = None  # Not easily available without more data

    dxy_val = market_data.get("dxy", {}).get("value")
    dxy_trend = market_data.get("dxy", {}).get("trend", "stable")
    dxy_5d = market_data.get("dxy", {}).get("change_5d")

    tnx_val = market_data.get("tnx", {}).get("value")
    tnx_trend = market_data.get("tnx", {}).get("trend", "stable")

    output = {
        "generated": iso_ts,
        "run_time": run_time_str,
        "run_type": run_type,
        "version": "1.1",
        "overall": bias_data.get("overall", {}),
        "asset_classes": bias_data.get("asset_classes", {}),
        "market_data": {
            "vix": {
                "value": vix_val,
                "trend": vix_trend,
                "change_1d_pct": vix_chg,
            },
            "dxy": {
                "value": dxy_val,
                "trend": dxy_trend,
                "change_5d": dxy_5d,
            },
            "us10y": {
                "value": tnx_val,
                "trend": tnx_trend,
            },
            "real_yield_10y": {
                "value": fred_data.get("real_yield_10y"),
                "trend": "stable",
            },
            "hy_spread": {
                "value": fred_data.get("hy_spread"),
                "trend": "stable",
            },
            "fed_funds_current": fred_data.get("fedfunds"),
            "breakeven_inflation_10y": fred_data.get("breakeven_10y"),
            "gold": market_data.get("gold", {}).get("value"),
            "crude_oil": market_data.get("crude", {}).get("value"),
            "btc": market_data.get("btc", {}).get("value"),
            "sp500": market_data.get("sp500", {}).get("value"),
            "nasdaq": market_data.get("nasdaq", {}).get("value"),
        },
        "calendar": calendar,
        "key_drivers": bias_data.get("key_drivers", []),
        "data_quality": {
            "stale_sources": stale_yf + stale_fred,
            "fallbacks_used": stale_yf + stale_fred,
            "validation_corrections": validation_errors,
            "notes": f"Generated by Matrix Nano Bias Script v1.1 | Run: {run_type}",
        },
    }
    return output


def build_markdown_summary(output, bias_data, market_data, fred_data, calendar, run_type, now_et):
    """Build the executive summary Markdown file."""
    date_str = now_et.strftime("%B %d, %Y")
    time_str = now_et.strftime("%H:%M")

    overall_id = bias_data.get("overall", {})
    ov_intra = overall_id.get("intraday", {})
    ov_swing = overall_id.get("swing", {})

    ac = bias_data.get("asset_classes", {})

    def row(name, cls):
        i = cls.get("intraday", {})
        s = cls.get("swing", {})
        i_score = i.get("score", 0)
        s_score = s.get("score", 0)
        i_sig = i.get("signal", "N/A")
        s_sig = s.get("signal", "N/A")
        i_conf = i.get("confidence", 0)
        s_conf = s.get("confidence", 0)
        avg_conf = (i_conf + s_conf) // 2
        return f"| {name} | {i_sig} ({i_score:+d}) | {s_sig} ({s_score:+d}) | {avg_conf}/10 |"

    vix = market_data.get("vix", {}).get("value", "N/A")
    dxy = market_data.get("dxy", {}).get("value", "N/A")
    tnx = market_data.get("tnx", {}).get("value", "N/A")
    hy = fred_data.get("hy_spread", "N/A")
    hy_str = f"{hy:.0f}" if isinstance(hy, float) else str(hy)

    vix_trend = market_data.get("vix", {}).get("trend", "stable").capitalize()
    dxy_trend = market_data.get("dxy", {}).get("trend", "stable").capitalize()
    tnx_trend = market_data.get("tnx", {}).get("trend", "stable").capitalize()

    vix_impl = "Risk-on supportive" if isinstance(vix, float) and vix < 20 else ("Elevated fear" if isinstance(vix, float) and vix > 25 else "Moderate risk")
    dxy_impl = "Commodity/risk tailwind" if dxy_trend == "Falling" else ("Headwind for risk assets" if dxy_trend == "Rising" else "Neutral")
    tnx_impl = "Pressure on equities" if tnx_trend == "Rising" else ("Supportive for equities" if tnx_trend == "Falling" else "Neutral")
    hy_impl = "Credit stress low" if isinstance(hy, float) and hy < 400 else ("Credit stress elevated" if isinstance(hy, float) and hy > 500 else "Moderate credit risk")

    calendar_section = ""
    if calendar.get("high_impact_today"):
        events = ", ".join(calendar.get("high_impact_events", []))
        calendar_section = f"\n> **High-Impact Events Today:** {events} — Confidence reduced per news impact rules.\n"

    key_drivers = bias_data.get("key_drivers", [])
    drivers_text = "\n".join([f"{i+1}. **{d.split(':')[0] if ':' in d else 'Theme'}:** {d}" for i, d in enumerate(key_drivers)])

    exec_summary = bias_data.get("executive_summary", "Market analysis complete. See detailed sections below.")

    md = f"""# Matrix Nano Daily Bias Report
**Date:** {date_str} | **Time:** {time_str} ET | **Run Type:** {run_type}

---

## Overall Market Bias
**Intraday:** {ov_intra.get('signal', 'N/A')} ({ov_intra.get('score', 0):+d}) | Confidence: {ov_intra.get('confidence', 0)}/10
**Swing:** {ov_swing.get('signal', 'N/A')} ({ov_swing.get('score', 0):+d}) | Confidence: {ov_swing.get('confidence', 0)}/10

{exec_summary}
{calendar_section}
---

## Asset Class Summary

| Asset Class | Intraday | Swing | Avg Confidence |
|-------------|----------|-------|----------------|
{row('EQUITY_INDEX', ac.get('EQUITY_INDEX', {}))}
{row('FIXED_INCOME', ac.get('FIXED_INCOME', {}))}
{row('ENERGY', ac.get('ENERGY', {}))}
{row('METALS', ac.get('METALS', {}))}
{row('AGRICULTURE', ac.get('AGRICULTURE', {}))}
{row('FX', ac.get('FX', {}))}
{row('CRYPTO', ac.get('CRYPTO', {}))}
{row('VOLATILITY', ac.get('VOLATILITY', {}))}

---

## Detailed Asset Class Analysis

### EQUITY_INDEX
**Symbols:** ES, NQ, YM, RTY, MES, MNQ, MYM, M2K
**Intraday:** {ac.get('EQUITY_INDEX', {}).get('intraday', {}).get('signal', 'N/A')} ({ac.get('EQUITY_INDEX', {}).get('intraday', {}).get('score', 0):+d}) | **Swing:** {ac.get('EQUITY_INDEX', {}).get('swing', {}).get('signal', 'N/A')} ({ac.get('EQUITY_INDEX', {}).get('swing', {}).get('score', 0):+d})

{ac.get('EQUITY_INDEX', {}).get('intraday', {}).get('reason', '')} | Swing: {ac.get('EQUITY_INDEX', {}).get('swing', {}).get('reason', '')}

### FIXED_INCOME
**Symbols:** ZB, ZN, ZT, ZF, GE, SR3
**Intraday:** {ac.get('FIXED_INCOME', {}).get('intraday', {}).get('signal', 'N/A')} ({ac.get('FIXED_INCOME', {}).get('intraday', {}).get('score', 0):+d}) | **Swing:** {ac.get('FIXED_INCOME', {}).get('swing', {}).get('signal', 'N/A')} ({ac.get('FIXED_INCOME', {}).get('swing', {}).get('score', 0):+d})

{ac.get('FIXED_INCOME', {}).get('intraday', {}).get('reason', '')} | Swing: {ac.get('FIXED_INCOME', {}).get('swing', {}).get('reason', '')}

### ENERGY
**Symbols:** CL, NG, RB, HO, MCL
**Intraday:** {ac.get('ENERGY', {}).get('intraday', {}).get('signal', 'N/A')} ({ac.get('ENERGY', {}).get('intraday', {}).get('score', 0):+d}) | **Swing:** {ac.get('ENERGY', {}).get('swing', {}).get('signal', 'N/A')} ({ac.get('ENERGY', {}).get('swing', {}).get('score', 0):+d})

{ac.get('ENERGY', {}).get('intraday', {}).get('reason', '')} | Swing: {ac.get('ENERGY', {}).get('swing', {}).get('reason', '')}

### METALS
**Symbols:** GC, SI, HG, MGC
**Intraday:** {ac.get('METALS', {}).get('intraday', {}).get('signal', 'N/A')} ({ac.get('METALS', {}).get('intraday', {}).get('score', 0):+d}) | **Swing:** {ac.get('METALS', {}).get('swing', {}).get('signal', 'N/A')} ({ac.get('METALS', {}).get('swing', {}).get('score', 0):+d})

{ac.get('METALS', {}).get('intraday', {}).get('reason', '')} | Swing: {ac.get('METALS', {}).get('swing', {}).get('reason', '')}

### AGRICULTURE
**Symbols:** ZC, ZS, ZW, ZM, ZL, KC, SB, CC, CT
**Intraday:** {ac.get('AGRICULTURE', {}).get('intraday', {}).get('signal', 'N/A')} ({ac.get('AGRICULTURE', {}).get('intraday', {}).get('score', 0):+d}) | **Swing:** {ac.get('AGRICULTURE', {}).get('swing', {}).get('signal', 'N/A')} ({ac.get('AGRICULTURE', {}).get('swing', {}).get('score', 0):+d})

{ac.get('AGRICULTURE', {}).get('intraday', {}).get('reason', '')} | Swing: {ac.get('AGRICULTURE', {}).get('swing', {}).get('reason', '')}

### FX
**Symbols:** 6E, 6A, 6J, 6B, M6E (positive = bearish USD)
**Intraday:** {ac.get('FX', {}).get('intraday', {}).get('signal', 'N/A')} ({ac.get('FX', {}).get('intraday', {}).get('score', 0):+d}) | **Swing:** {ac.get('FX', {}).get('swing', {}).get('signal', 'N/A')} ({ac.get('FX', {}).get('swing', {}).get('score', 0):+d})

{ac.get('FX', {}).get('intraday', {}).get('reason', '')} | Swing: {ac.get('FX', {}).get('swing', {}).get('reason', '')}

### CRYPTO
**Symbols:** BTC, ETH, MBT
**Intraday:** {ac.get('CRYPTO', {}).get('intraday', {}).get('signal', 'N/A')} ({ac.get('CRYPTO', {}).get('intraday', {}).get('score', 0):+d}) | **Swing:** {ac.get('CRYPTO', {}).get('swing', {}).get('signal', 'N/A')} ({ac.get('CRYPTO', {}).get('swing', {}).get('score', 0):+d})

{ac.get('CRYPTO', {}).get('intraday', {}).get('reason', '')} | Swing: {ac.get('CRYPTO', {}).get('swing', {}).get('reason', '')}

### VOLATILITY
**Symbols:** VX, VXM (negative = low vol / sell premium)
**Intraday:** {ac.get('VOLATILITY', {}).get('intraday', {}).get('signal', 'N/A')} ({ac.get('VOLATILITY', {}).get('intraday', {}).get('score', 0):+d}) | **Swing:** {ac.get('VOLATILITY', {}).get('swing', {}).get('signal', 'N/A')} ({ac.get('VOLATILITY', {}).get('swing', {}).get('score', 0):+d})

{ac.get('VOLATILITY', {}).get('intraday', {}).get('reason', '')} | Swing: {ac.get('VOLATILITY', {}).get('swing', {}).get('reason', '')}

---

## Key Market Data

| Indicator | Value | Trend | Implication |
|-----------|-------|-------|-------------|
| VIX | {vix} | {vix_trend} | {vix_impl} |
| DXY | {dxy} | {dxy_trend} | {dxy_impl} |
| 10Y Yield | {tnx}% | {tnx_trend} | {tnx_impl} |
| HY Spread | {hy_str} bps | Stable | {hy_impl} |

---

## Key Macro Themes

{drivers_text}

---

## Upcoming Catalysts

### Next 24 Hours
- Monitor overnight futures for continuation or reversal signals
- Watch for any Fed speaker commentary

### This Week
- NFP in {calendar.get('nfp_days_away', 'N/A')} days — elevated uncertainty approaching
- FOMC in {calendar.get('fomc_days_away', 'N/A')} days — policy clarity pending

---

## Risk Factors & Caveats

- All data sourced from Yahoo Finance and FRED at time of generation
- Stale sources (if any): {', '.join(output.get('data_quality', {}).get('stale_sources', [])) or 'None'}
- Validation corrections applied: {len(output.get('data_quality', {}).get('validation_corrections', []))}

---

**Data Sources:** Yahoo Finance, FRED, ForexFactory
**Generated:** {output.get('generated', 'N/A')}
**Version:** 1.1

---
**End of Report**
"""
    return md


# ─────────────────────────────────────────────
# GIT OPERATIONS
# ─────────────────────────────────────────────

def git_commit_and_push(output_json, exec_md, run_type, now_et, bias_data):
    """Write files, commit, and push to GitHub."""
    archive_ts = now_et.strftime("%Y-%m-%d_%H%M_ET")

    # Paths
    latest_json_path = os.path.join(REPO_DIR, "data", "bias_scores", "latest.json")
    archive_json_path = os.path.join(REPO_DIR, "data", "bias_scores", "archive", f"{archive_ts}.json")
    latest_md_path = os.path.join(REPO_DIR, "data", "executive_summaries", "latest.md")
    archive_md_path = os.path.join(REPO_DIR, "data", "executive_summaries", "archive", f"{archive_ts}.md")

    # Ensure archive dirs exist
    os.makedirs(os.path.dirname(archive_json_path), exist_ok=True)
    os.makedirs(os.path.dirname(archive_md_path), exist_ok=True)

    json_str = json.dumps(output_json, indent=2)

    # Write files
    with open(latest_json_path, "w") as f:
        f.write(json_str)
    with open(archive_json_path, "w") as f:
        f.write(json_str)
    with open(latest_md_path, "w") as f:
        f.write(exec_md)
    with open(archive_md_path, "w") as f:
        f.write(exec_md)

    print(f"[OK] Files written: {latest_json_path}, {archive_json_path}")

    # Build commit message
    ov_intra = bias_data.get("overall", {}).get("intraday", {})
    ov_swing = bias_data.get("overall", {}).get("swing", {})
    ac = bias_data.get("asset_classes", {})

    def sig(cls, tf):
        return ac.get(cls, {}).get(tf, {}).get("signal", "N/A")

    def sc(cls, tf):
        return ac.get(cls, {}).get(tf, {}).get("score", 0)

    date_str = now_et.strftime("%Y-%m-%d %H:%M ET")
    # Commit message format per v1.2 spec
    ov_intra_sig = ov_intra.get('signal', 'N/A')
    ov_intra_sc = ov_intra.get('score', 0)
    ov_conf = ov_intra.get('confidence', 0)
    commit_msg = f"""Bias Update: {date_str} ({run_type})

Overall: {ov_intra_sig} ({ov_intra_sc:+d}) | Confidence: {ov_conf}
Indices: {sig('EQUITY_INDEX', 'intraday')} ({sc('EQUITY_INDEX', 'intraday'):+d}) | Metals: {sig('METALS', 'intraday')} ({sc('METALS', 'intraday'):+d})
Energy: {sig('ENERGY', 'intraday')} ({sc('ENERGY', 'intraday'):+d}) | FX: {sig('FX', 'intraday')} ({sc('FX', 'intraday'):+d})"""

    # Git operations
    cmds = [
        f"cd {REPO_DIR} && git config user.email 'manus-bot@matrix-nano.ai'",
        f"cd {REPO_DIR} && git config user.name 'Manus Bias Bot'",
        f"cd {REPO_DIR} && git add data/",
        f"cd {REPO_DIR} && git commit -m '{commit_msg.replace(chr(39), chr(34))}'",
        f"cd {REPO_DIR} && git push origin main",
    ]

    for cmd in cmds:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[WARN] Git command failed: {cmd}\n{result.stderr}")
        else:
            print(f"[OK] {cmd.split('&&')[-1].strip()}")

    return archive_ts


# ─────────────────────────────────────────────
# VERIFICATION
# ─────────────────────────────────────────────

def verify_commit():
    """Fetch the committed latest.json from GitHub and verify it's valid."""
    url = "https://raw.githubusercontent.com/joenathanthompson-arch/matrix-nano-reports/main/data/bias_scores/latest.json"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        assert "overall" in data, "Missing 'overall'"
        assert "asset_classes" in data, "Missing 'asset_classes'"
        assert len(data["asset_classes"]) >= 8, "Missing asset classes"
        print(f"[OK] Verification passed. Generated: {data.get('generated', 'N/A')}")
        return True
    except Exception as e:
        print(f"[ERROR] Verification failed: {e}")
        return False


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    now_et = datetime.now(ET_TZ)
    hour = now_et.hour
    run_type = "PRE" if (hour < 12) else "EOD"

    print(f"\n{'='*60}")
    print(f"Matrix Nano Bias Generation")
    print(f"Run Time: {now_et.strftime('%Y-%m-%d %H:%M ET')} | Type: {run_type}")
    print(f"{'='*60}\n")

    # Step 1: Fetch data
    print("[1/6] Fetching Yahoo Finance data...")
    market_data, stale_yf = fetch_yfinance_data()
    print(f"      VIX={market_data.get('vix', {}).get('value', 'N/A')} | DXY={market_data.get('dxy', {}).get('value', 'N/A')} | Gold={market_data.get('gold', {}).get('value', 'N/A')}")

    print("[2/6] Fetching FRED economic data...")
    fred_data, stale_fred = fetch_fred_data()
    print(f"      Fed Funds={fred_data.get('fedfunds', 'N/A')}% | HY Spread={fred_data.get('hy_spread', 'N/A')}bps | Real Yield={fred_data.get('real_yield_10y', 'N/A')}%")

    print("[3/6] Checking economic calendar...")
    calendar = fetch_economic_calendar()
    print(f"      High-impact today: {calendar['high_impact_today']} | Events: {calendar['high_impact_events']}")

    # Step 2: LLM analysis
    print("[4/6] Calling LLM for bias analysis...")
    prompt = build_analysis_prompt(market_data, fred_data, calendar, run_type, now_et)

    try:
        llm_response = call_llm(prompt)
        # Strip any accidental markdown code blocks
        llm_response = llm_response.strip()
        if llm_response.startswith("```"):
            llm_response = llm_response.split("```")[1]
            if llm_response.startswith("json"):
                llm_response = llm_response[4:]
        bias_data = json.loads(llm_response)
        print("      LLM response received and parsed successfully.")
    except Exception as e:
        print(f"[ERROR] LLM call failed: {e}")
        print(f"        Raw response: {llm_response[:500] if 'llm_response' in dir() else 'N/A'}")
        # Fallback: all neutral
        bias_data = {
            "overall": {
                "intraday": {"score": 0, "signal": "NEUTRAL", "confidence": 1, "reason": "LLM analysis failed - defaulting to neutral"},
                "swing": {"score": 0, "signal": "NEUTRAL", "confidence": 1, "reason": "LLM analysis failed - defaulting to neutral"},
            },
            "asset_classes": {},
            "key_drivers": ["LLM analysis failed - all scores defaulted to neutral"],
            "executive_summary": "Analysis failed. All scores set to NEUTRAL with minimum confidence.",
        }

    # Step 3: Validate
    print("[5/6] Validating and building output...")
    bias_data, validation_errors = validate_and_fix(bias_data)
    if validation_errors:
        print(f"      Validation corrections: {validation_errors}")

    output_json = build_json_output(bias_data, market_data, fred_data, calendar, run_type, now_et, stale_yf, stale_fred, validation_errors)
    exec_md = build_markdown_summary(output_json, bias_data, market_data, fred_data, calendar, run_type, now_et)

    # Step 4: Commit
    print("[6/6] Committing to GitHub...")
    archive_ts = git_commit_and_push(output_json, exec_md, run_type, now_et, bias_data)

    # Step 5: Verify
    print("\nVerifying commit...")
    import time
    time.sleep(3)  # Brief wait for GitHub to process
    verify_commit()

    print(f"\n{'='*60}")
    print(f"Matrix Nano Bias Generation COMPLETE")
    print(f"Archive: {archive_ts}")
    print(f"{'='*60}\n")

    return output_json


if __name__ == "__main__":
    main()
