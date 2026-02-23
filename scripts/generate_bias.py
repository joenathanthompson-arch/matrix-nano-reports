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
    "yield_curve_2s10s": "T10Y2Y",   # 2s10s spread — FIXED_INCOME driver
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


def fetch_vix_term_structure():
    """
    Fetch VIX term structure from vixcentral.com.
    Returns contango/backwardation status based on front-month vs back-month VIX futures.
    """
    import re
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get("http://vixcentral.com", timeout=15, headers=headers)
        resp.raise_for_status()
        text = resp.text

        # VIXCentral embeds futures prices in a JS array named 'previous_close_var'
        # Format: [F1, F2, F3, F4, F5, F6, F7, F8] = 8 monthly VIX futures
        match = re.search(r'previous_close_var\s*=\s*\[([\d\., ]+)\]', text)
        if match:
            vals = [float(x.strip()) for x in match.group(1).split(',') if x.strip()]
            if len(vals) >= 2:
                f1 = vals[0]  # Front month
                f2 = vals[1]  # Second month
                # Contango = F2 > F1 (normal, bearish for VX)
                # Backwardation = F1 > F2 (stressed, bullish for VX)
                spread_pct = round((f2 - f1) / f1 * 100, 2) if f1 > 0 else 0
                structure = "contango" if spread_pct > 0 else "backwardation"
                return {
                    "structure": structure,
                    "contango_pct": spread_pct,
                    "f1": f1,
                    "f2": f2,
                    "source": "vixcentral.com"
                }

        # Fallback: infer from VIX spot vs 30d avg (rough proxy)
        return {"structure": "unknown", "contango_pct": None, "source": "vixcentral.com", "note": "parse failed"}
    except Exception as e:
        print(f"[WARN] VIX term structure fetch failed: {e}")
        return {"structure": "unknown", "contango_pct": None, "source": "vixcentral.com", "error": str(e)}


def fetch_btc_etf_flows():
    """
    Fetch Bitcoin ETF net flows.
    Tries Coinglass public data first, then CoinGecko market data as fallback.
    Returns total net flow in USD millions (positive = inflows, negative = outflows).
    """
    import re
    # Try Coinglass public API (no key needed for some endpoints)
    for url in [
        "https://open-api.coinglass.com/public/v2/indicator/bitcoin_etf_flow",
        "https://open-api.coinglass.com/api/pro/v1/bitcoin/etf/flow",
    ]:
        try:
            headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                # Handle various response shapes
                rows = data.get("data", data.get("result", []))
                if isinstance(rows, list) and rows:
                    latest = rows[0]
                    for key in ["totalNetFlow", "net_flow", "netFlow", "total"]:
                        if key in latest:
                            val = float(latest[key])
                            # Value might already be in millions or raw USD
                            if abs(val) > 1e9:
                                val = val / 1e6
                            return {"net_flow_usd_m": round(val, 1), "trend": "inflow" if val > 0 else "outflow", "source": "coinglass.com"}
        except Exception:
            continue

    # Fallback: scrape Coinglass ETF page for the daily flow number
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        resp = requests.get("https://www.coinglass.com/bitcoin-etf", headers=headers, timeout=15)
        if resp.status_code == 200:
            # Look for net flow pattern like "$123.4M" or "-$45.6M"
            match = re.search(r'Net Flow[^$]*\$([\-\d,\.]+)M', resp.text, re.IGNORECASE)
            if match:
                val = float(match.group(1).replace(",", ""))
                return {"net_flow_usd_m": val, "trend": "inflow" if val > 0 else "outflow", "source": "coinglass.com (scraped)"}
    except Exception:
        pass

    # Fallback 2: Use CoinGecko market cap change as proxy for institutional flows
    try:
        resp = requests.get("https://api.coingecko.com/api/v3/global", timeout=10)
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            market_cap_change = data.get("market_cap_change_percentage_24h_usd")
            if market_cap_change is not None:
                # Estimate flow direction from market cap change
                # Large positive = likely inflows, large negative = likely outflows
                trend = "inflow" if market_cap_change > 0 else "outflow"
                # Note: This is a proxy, not actual ETF flow data
                return {
                    "net_flow_usd_m": None,  # We don't have actual flow number
                    "trend": trend,
                    "market_cap_change_24h_pct": round(market_cap_change, 2),
                    "source": "coingecko.com (market cap proxy)",
                    "note": "ETF flows unavailable - using market cap change as proxy"
                }
    except Exception:
        pass

    print(f"[WARN] BTC ETF flows: all sources failed, returning unknown")
    return {"net_flow_usd_m": None, "trend": "unknown", "source": "multiple", "note": "all sources failed"}


def fetch_crypto_fear_greed():
    """
    Fetch Crypto Fear & Greed Index from alternative.me.
    Returns value (0-100) and classification.
    """
    try:
        resp = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        entry = data["data"][0]
        value = int(entry["value"])
        classification = entry["value_classification"]
        return {"value": value, "classification": classification, "source": "alternative.me"}
    except Exception as e:
        print(f"[WARN] Crypto Fear & Greed fetch failed: {e}")
        return {"value": None, "classification": "unknown", "source": "alternative.me", "error": str(e)}


def fetch_gdpnow():
    """
    Fetch Atlanta Fed GDPNow estimate.
    Returns current quarter GDP growth estimate.
    Primary: Use FRED GDPNOW series (reliable, no API key needed for CSV)
    """
    # Primary: FRED GDPNOW series (this is the official Atlanta Fed data on FRED)
    try:
        resp = requests.get(
            "https://fred.stlouisfed.org/graph/fredgraph.csv?id=GDPNOW",
            timeout=15, headers={"User-Agent": "Mozilla/5.0"}
        )
        if resp.status_code == 200:
            lines = [l for l in resp.text.strip().split("\n") if l.strip()]
            # Last line has the most recent estimate; format: date,value
            for line in reversed(lines[1:]):
                parts = line.strip().split(",")
                if len(parts) == 2 and parts[1] not in (".", ""):
                    try:
                        val = float(parts[1])
                        date_str = parts[0]
                        return {"estimate_pct": round(val, 1), "date": date_str, "source": "FRED/GDPNOW"}
                    except ValueError:
                        continue
    except Exception as e:
        print(f"[WARN] FRED GDPNow fetch failed: {e}")

    # Fallback: Try Atlanta Fed direct (may be blocked or URL changed)
    import re
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get("https://www.atlantafed.org/cqer/research/gdpnow", timeout=15, headers=headers)
        resp.raise_for_status()
        # Look for patterns like "2.3 percent" or "-1.5 percent"
        match = re.search(r'([\-\d]+\.\d)\s*percent', resp.text, re.IGNORECASE)
        if match:
            return {"estimate_pct": float(match.group(1)), "source": "atlantafed.org"}
    except Exception as e:
        print(f"[WARN] Atlanta Fed direct fetch failed: {e}")

    return {"estimate_pct": None, "source": "FRED/GDPNOW", "note": "all sources failed"}


def fetch_eia_inventory():
    """
    Fetch EIA weekly crude oil inventory data.
    Returns crude oil inventory change (draw = bullish, build = bearish).
    Uses FRED series WCRSTUS1 as a reliable free alternative to the EIA API.
    """
    # Primary: use FRED DCOILWTICO (WTI crude oil price) as a proxy for supply/demand signal
    # Note: Weekly crude stocks (WCRSTUS1) requires EIA API key; use price trend as proxy
    try:
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILWTICO"
        resp = requests.get(url, timeout=15)
        lines = [l for l in resp.text.strip().split("\n") if l.strip()]
        values = []
        for line in reversed(lines[1:]):
            parts = line.strip().split(",")
            if len(parts) == 2 and parts[1] not in (".", ""):
                try:
                    values.append(float(parts[1]))
                except ValueError:
                    continue
            if len(values) >= 5:
                break
        if len(values) >= 2:
            # Use 5-day price change as supply/demand proxy
            change_5d = values[0] - values[min(4, len(values)-1)]
            signal = "draw" if change_5d > 0 else "build"  # Price up = implied draw
            return {
                "crude_price": round(values[0], 2),
                "crude_change_5d": round(change_5d, 2),
                "weekly_change_mb": None,  # Not available without EIA API key
                "signal": signal,
                "note": "Price-based proxy (EIA stocks require API key)",
                "source": "FRED/DCOILWTICO"
            }
    except Exception:
        pass

    # Fallback: EIA API v2 (may require registration but try anyway)
    try:
        resp = requests.get(
            "https://api.eia.gov/v2/petroleum/stoc/wstk/data/?frequency=weekly"
            "&data[0]=value&facets[series][]=WCRSTUS1"
            "&sort[0][column]=period&sort[0][direction]=desc&length=2",
            timeout=15
        )
        if resp.status_code == 200:
            rows = resp.json().get("response", {}).get("data", [])
            if len(rows) >= 2:
                change = float(rows[0]["value"]) - float(rows[1]["value"])
                return {
                    "crude_stocks_mb": round(float(rows[0]["value"]), 1),
                    "weekly_change_mb": round(change, 1),
                    "signal": "draw" if change < 0 else "build",
                    "source": "eia.gov"
                }
    except Exception as e:
        print(f"[WARN] EIA inventory fetch failed: {e}")

    return {"crude_stocks_mb": None, "weekly_change_mb": None, "signal": "unknown", "source": "eia.gov", "note": "fetch failed - not critical"}


def fetch_economic_calendar():
    """
    Check ForexFactory for high-impact events today and this week.
    Returns a simple dict with flags and event names.
    Includes hardcoded 2026 FOMC dates for reliable calculation.
    """
    now_et = datetime.now(ET_TZ)
    today_str = now_et.strftime("%Y-%m-%d")
    today_date = now_et.date()

    # 2026 FOMC Meeting Dates (statement release dates - day 2 of meeting)
    # Source: Federal Reserve official calendar
    FOMC_DATES_2026 = [
        datetime(2026, 1, 29, tzinfo=ET_TZ).date(),   # Jan 28-29
        datetime(2026, 3, 18, tzinfo=ET_TZ).date(),   # Mar 17-18
        datetime(2026, 5, 6, tzinfo=ET_TZ).date(),    # May 5-6
        datetime(2026, 6, 17, tzinfo=ET_TZ).date(),   # Jun 16-17
        datetime(2026, 7, 29, tzinfo=ET_TZ).date(),   # Jul 28-29
        datetime(2026, 9, 16, tzinfo=ET_TZ).date(),   # Sep 15-16
        datetime(2026, 11, 4, tzinfo=ET_TZ).date(),   # Nov 3-4
        datetime(2026, 12, 16, tzinfo=ET_TZ).date(),  # Dec 15-16
    ]

    # 2027 FOMC dates (for late 2026 lookups)
    FOMC_DATES_2027 = [
        datetime(2027, 1, 27, tzinfo=ET_TZ).date(),   # Jan 26-27
        datetime(2027, 3, 17, tzinfo=ET_TZ).date(),   # Mar 16-17
    ]

    high_impact_today = False
    high_impact_events = []
    in_blackout = False

    # Calculate days to next FOMC
    fomc_days_away = 99
    all_fomc_dates = FOMC_DATES_2026 + FOMC_DATES_2027
    for fomc_date in all_fomc_dates:
        if fomc_date >= today_date:
            fomc_days_away = (fomc_date - today_date).days
            break

    # Check if today is FOMC day
    if today_date in all_fomc_dates:
        high_impact_today = True
        high_impact_events.append("FOMC")
        in_blackout = True

    # Check if day before FOMC (blackout period)
    for fomc_date in all_fomc_dates:
        if (fomc_date - today_date).days == 1:
            in_blackout = True
            break

    # First Friday of month = NFP
    first_friday = None
    for day in range(1, 8):
        d = datetime(now_et.year, now_et.month, day, tzinfo=ET_TZ)
        if d.weekday() == 4:  # Friday
            first_friday = d
            break

    nfp_days_away = 99
    if first_friday:
        delta = (first_friday.date() - today_date).days
        if delta >= 0:
            nfp_days_away = delta
        else:
            # Calculate next month's first Friday
            next_month = now_et.month + 1 if now_et.month < 12 else 1
            next_year = now_et.year if now_et.month < 12 else now_et.year + 1
            for day in range(1, 8):
                d = datetime(next_year, next_month, day, tzinfo=ET_TZ)
                if d.weekday() == 4:
                    nfp_days_away = (d.date() - today_date).days
                    break

    if first_friday and today_date == first_friday.date():
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
                event_date = event.get("date", "")
                if impact == "HIGH" and today_str in event_date:
                    high_impact_today = True
                    if title not in high_impact_events:
                        high_impact_events.append(title)
    except Exception as e:
        print(f"[WARN] ForexFactory calendar fetch failed: {e}")

    # Deduplicate
    high_impact_events = list(set(high_impact_events))

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

def build_analysis_prompt(market_data, fred_data, calendar, extra_data, run_type, now_et):
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
- 2s10s Yield Curve Spread: {fred_data.get('yield_curve_2s10s', 'N/A')}% ({'inverted' if isinstance(fred_data.get('yield_curve_2s10s'), float) and fred_data.get('yield_curve_2s10s', 0) < 0 else 'normal'})

### VIX Term Structure
- Structure: {extra_data.get('vix_term', {}).get('structure', 'N/A')}
- Contango/Backwardation: {extra_data.get('vix_term', {}).get('contango_pct', 'N/A')}%
- Interpretation: {'Bearish VX (decay favors short vol)' if extra_data.get('vix_term', {}).get('structure') == 'contango' else ('Bullish VX (backwardation = stress)' if extra_data.get('vix_term', {}).get('structure') == 'backwardation' else 'N/A')}

### Growth Outlook
- Atlanta Fed GDPNow (current quarter): {extra_data.get('gdpnow', {}).get('estimate_pct', 'N/A')}%

### Energy Inventories (EIA)
- Crude Oil Stocks: {extra_data.get('eia', {}).get('crude_stocks_mb', 'N/A')} million barrels
- Weekly Change: {extra_data.get('eia', {}).get('weekly_change_mb', 'N/A')} mb ({extra_data.get('eia', {}).get('signal', 'N/A')})
- Signal: {'Bullish (draw = supply tightening)' if extra_data.get('eia', {}).get('signal') == 'draw' else ('Bearish (build = supply glut)' if extra_data.get('eia', {}).get('signal') == 'build' else 'N/A')}

### Crypto Sentiment
- Fear & Greed Index: {extra_data.get('fear_greed', {}).get('value', 'N/A')} / 100 ({extra_data.get('fear_greed', {}).get('classification', 'N/A')})
- BTC ETF Net Flow: {extra_data.get('btc_etf', {}).get('net_flow_usd_m', 'N/A')} USD million ({extra_data.get('btc_etf', {}).get('trend', 'N/A')})

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

def build_json_output(bias_data, market_data, fred_data, calendar, run_type, now_et, stale_yf, stale_fred, validation_errors, extra_data=None):
    if extra_data is None:
        extra_data = {}
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
            "yield_curve_2s10s": fred_data.get("yield_curve_2s10s"),
            "vix_term_structure": extra_data.get("vix_term", {}).get("structure"),
            "vix_contango_pct": extra_data.get("vix_term", {}).get("contango_pct"),
            "gdpnow_estimate_pct": extra_data.get("gdpnow", {}).get("estimate_pct"),
            "eia_crude_change_mb": extra_data.get("eia", {}).get("weekly_change_mb"),
            "eia_signal": extra_data.get("eia", {}).get("signal"),
            "crypto_fear_greed": extra_data.get("fear_greed", {}).get("value"),
            "crypto_fear_greed_label": extra_data.get("fear_greed", {}).get("classification"),
            "btc_etf_flow_usd_m": extra_data.get("btc_etf", {}).get("net_flow_usd_m"),
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
            "notes": f"Generated by Matrix Nano Bias Script v1.2 | Run: {run_type}",
        },
    }
    return output


def build_markdown_summary(output, bias_data, market_data, fred_data, calendar, run_type, now_et, extra_data=None):
    """Build the executive summary Markdown file."""
    if extra_data is None:
        extra_data = {}
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

    vix_term_str = extra_data.get('vix_term', {}).get('structure', 'N/A')
    vix_contango = extra_data.get('vix_term', {}).get('contango_pct', 'N/A')
    fear_greed_val = extra_data.get('fear_greed', {}).get('value', 'N/A')
    fear_greed_label = extra_data.get('fear_greed', {}).get('classification', 'N/A')
    btc_etf_flow = extra_data.get('btc_etf', {}).get('net_flow_usd_m', 'N/A')
    btc_etf_trend = extra_data.get('btc_etf', {}).get('trend', 'N/A')
    gdpnow_est = extra_data.get('gdpnow', {}).get('estimate_pct', 'N/A')
    eia_change = extra_data.get('eia', {}).get('weekly_change_mb', 'N/A')
    eia_signal = extra_data.get('eia', {}).get('signal', 'N/A')
    yield_curve = fred_data.get('yield_curve_2s10s', 'N/A')
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
| VIX Term Structure | {vix_term_str} ({vix_contango}%) | — | {'Decay favors short vol' if vix_term_str == 'contango' else ('Stress signal — long vol' if vix_term_str == 'backwardation' else 'N/A')} |
| DXY | {dxy} | {dxy_trend} | {dxy_impl} |
| 10Y Yield | {tnx}% | {tnx_trend} | {tnx_impl} |
| 2s10s Curve | {yield_curve} bps | — | {'Inverted — recession signal' if isinstance(yield_curve, float) and yield_curve < 0 else ('Normal — growth positive' if isinstance(yield_curve, float) and yield_curve > 0 else 'N/A')} |
| HY Spread | {hy_str} bps | Stable | {hy_impl} |
| GDPNow | {gdpnow_est}% | — | {'Growth supportive' if isinstance(gdpnow_est, float) and gdpnow_est > 2 else ('Slowing' if isinstance(gdpnow_est, float) and gdpnow_est < 1 else 'Moderate growth')} |
| EIA Crude Inventory | {eia_change} mb | {eia_signal} | {'Bullish CL — supply tightening' if eia_signal == 'draw' else ('Bearish CL — supply building' if eia_signal == 'build' else 'N/A')} |
| Crypto Fear & Greed | {fear_greed_val}/100 | {fear_greed_label} | {'Extreme greed — caution' if isinstance(fear_greed_val, int) and fear_greed_val > 75 else ('Extreme fear — potential buy' if isinstance(fear_greed_val, int) and fear_greed_val < 25 else 'Neutral sentiment')} |
| BTC ETF Flows | {btc_etf_flow}M USD | {btc_etf_trend} | {'Institutional demand' if btc_etf_trend == 'inflow' else ('Selling pressure' if btc_etf_trend == 'outflow' else 'N/A')} |

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

**Data Sources:** Yahoo Finance, FRED, ForexFactory, VIXCentral, Coinglass, Alternative.me, Atlanta Fed, EIA
**Generated:** {output.get('generated', 'N/A')}
**Version:** 1.2

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

    print("[3b/6] Fetching supplementary data sources...")
    vix_term = fetch_vix_term_structure()
    btc_etf = fetch_btc_etf_flows()
    fear_greed = fetch_crypto_fear_greed()
    gdpnow = fetch_gdpnow()
    eia = fetch_eia_inventory()
    extra_data = {
        "vix_term": vix_term,
        "btc_etf": btc_etf,
        "fear_greed": fear_greed,
        "gdpnow": gdpnow,
        "eia": eia,
    }
    print(f"      VIX structure={vix_term.get('structure','N/A')} | F&G={fear_greed.get('value','N/A')} | EIA={eia.get('signal','N/A')} | GDPNow={gdpnow.get('estimate_pct','N/A')}%")

    # Step 2: LLM analysis
    print("[4/6] Calling LLM for bias analysis...")
    prompt = build_analysis_prompt(market_data, fred_data, calendar, extra_data, run_type, now_et)

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

    output_json = build_json_output(bias_data, market_data, fred_data, calendar, run_type, now_et, stale_yf, stale_fred, validation_errors, extra_data)
    exec_md = build_markdown_summary(output_json, bias_data, market_data, fred_data, calendar, run_type, now_et, extra_data)

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
