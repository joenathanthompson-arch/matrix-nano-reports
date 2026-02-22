# Matrix Nano Reports

Manus AI bias data for the Matrix Nano trading system.

## Version 2.1 Features

- **Dual Scoring** - Separate intraday and swing scores for each asset class
- **8 Asset Classes** - EQUITY_INDEX, FIXED_INCOME, ENERGY, METALS, AGRICULTURE, FX, CRYPTO, VOLATILITY
- **Swing-Optimized** - Swing scores consider longer-term factors (weekly trend, COT, positioning)

## Overview

Matrix Nano uses a **dual-score bias system**:
- **Intraday Scores** - For same-day IB breakout trading
- **Swing Scores** - For multi-day trend and Globex IB trades

The EA selects the appropriate score based on its `InpTradeStyle` setting.

## File Structure

```
matrix-nano-reports/
├── data/
│   ├── bias_scores/
│   │   ├── YYYY-MM-DD_HHMM.json   <- Timestamped archives
│   │   └── latest.json            <- EA READS THIS
│   └── executive_summaries/
│       ├── YYYY-MM-DD_HHMM.md     <- Timestamped archives
│       └── latest.md              <- /bias command reads this
└── docs/
    ├── BOOTSTRAP_PROMPT.md        <- Manus entry prompt (<5000 chars)
    └── MANUS_INSTRUCTIONS.md      <- Full methodology
```

## latest.json Format (v2.1)

```json
{
  "date": "2026-02-22",
  "generated_at": "2026-02-22T07:30:00Z",
  "methodology_version": "2.1_NANO",
  "overall": {
    "intraday": {"score": 2, "signal": "SLIGHT_BULLISH", "confidence": 6},
    "swing": {"score": 4, "signal": "BULLISH", "confidence": 7},
    "reason": "Risk-on sentiment, swing more bullish on multi-day trend"
  },
  "asset_classes": {
    "EQUITY_INDEX": {
      "intraday": {"score": 3, "signal": "BULLISH", "confidence": 7},
      "swing": {"score": 5, "signal": "BULLISH", "confidence": 8},
      "reason": "Tech earnings strong, weekly trend bullish"
    },
    "FIXED_INCOME": {
      "intraday": {"score": -2, "signal": "SLIGHT_BEARISH", "confidence": 6},
      "swing": {"score": -3, "signal": "SLIGHT_BEARISH", "confidence": 7},
      "reason": "Fed dovish but inflation sticky"
    },
    "ENERGY": {
      "intraday": {"score": 2, "signal": "SLIGHT_BULLISH", "confidence": 5},
      "swing": {"score": 3, "signal": "BULLISH", "confidence": 6},
      "reason": "Supply constraints, weak USD"
    },
    "METALS": {
      "intraday": {"score": 4, "signal": "BULLISH", "confidence": 7},
      "swing": {"score": 5, "signal": "BULLISH", "confidence": 8},
      "reason": "Falling real yields, safe-haven bid"
    },
    "AGRICULTURE": {
      "intraday": {"score": 1, "signal": "SLIGHT_BULLISH", "confidence": 5},
      "swing": {"score": 2, "signal": "SLIGHT_BULLISH", "confidence": 6},
      "reason": "Weather concerns, weak USD"
    },
    "FX": {
      "intraday": {"score": 0, "signal": "NEUTRAL", "confidence": 5},
      "swing": {"score": 1, "signal": "SLIGHT_BULLISH", "confidence": 6},
      "reason": "USD weakness favors swing longs"
    },
    "CRYPTO": {
      "intraday": {"score": 3, "signal": "BULLISH", "confidence": 6},
      "swing": {"score": 4, "signal": "BULLISH", "confidence": 7},
      "reason": "Risk-on sentiment, ETF inflows"
    },
    "VOLATILITY": {
      "intraday": {"score": -1, "signal": "SLIGHT_BEARISH", "confidence": 6},
      "swing": {"score": -2, "signal": "SLIGHT_BEARISH", "confidence": 7},
      "reason": "VIX subdued, low vol regime"
    }
  },
  "key_drivers": [
    "Fed maintaining dovish stance",
    "USD weakness supporting commodities",
    "Credit spreads stable"
  ],
  "data_quality": {
    "stale_sources": [],
    "fallbacks_used": [],
    "notes": "Dual intraday/swing scoring active"
  }
}
```

## Fields

### Overall Market Bias

| Field | Type | Description |
|-------|------|-------------|
| intraday | object | Intraday trading score/signal/confidence |
| swing | object | Swing trading score/signal/confidence |
| reason | string | Brief explanation |

### Score Object

| Field | Type | Description |
|-------|------|-------------|
| score | integer | -10 to +10 |
| signal | string | STRONG_BULLISH, BULLISH, SLIGHT_BULLISH, NEUTRAL, SLIGHT_BEARISH, BEARISH, STRONG_BEARISH |
| confidence | integer | 1-10 (affects position sizing) |

### 8 Asset Classes

| Asset Class | Symbols | Key Drivers |
|-------------|---------|-------------|
| **EQUITY_INDEX** | ES, NQ, YM, RTY | Fed, Real Yields, Credit, VIX |
| **FIXED_INCOME** | ZB, ZN, ZT, GE | Fed, Inflation, Supply, Curve |
| **ENERGY** | CL, NG, RB, HO | OPEC, Inventories, USD, Geopolitical |
| **METALS** | GC, SI, HG, PL | Real Yields, USD, Risk, China |
| **AGRICULTURE** | ZC, ZS, ZW, KC | Weather, USD, Demand, Inventories |
| **FX** | 6E, 6J, 6A, 6B | Rate Diffs, Central Banks, Risk |
| **CRYPTO** | BTC, ETH | Risk Sentiment, Flows, Regulation |
| **VOLATILITY** | VX | VIX Level, Term Structure, Events |

## Signal Mapping

| Score Range | Signal |
|-------------|--------|
| +7 to +10 | STRONG_BULLISH |
| +4 to +6 | BULLISH |
| +1 to +3 | SLIGHT_BULLISH |
| 0 | NEUTRAL |
| -1 to -3 | SLIGHT_BEARISH |
| -4 to -6 | BEARISH |
| -7 to -10 | STRONG_BEARISH |

## How Matrix Nano Uses This Data

The EA fetches `latest.json` and combines it with technical indicators:

```
Symbol Bias = (Overall x 0.25) + (Asset Class x 0.35) + (ALMA x 0.25) + (MACD x 0.15)
```

The EA reads intraday or swing scores based on `InpTradeStyle`:
- `STYLE_INTRADAY` → Uses `intraday` scores
- `STYLE_SWING` → Uses `swing` scores

### Confidence -> Position Sizing

| Confidence | Size Multiplier |
|------------|-----------------|
| 1 | 0.5x |
| 5 | 1.0x |
| 10 | 1.5x |

## Intraday vs Swing Factors

| Factor | Intraday Weight | Swing Weight |
|--------|-----------------|--------------|
| VIX Level | High | Medium |
| Session Timing | High | None |
| Daily IB | High | Low |
| Weekly Trend | Low | High |
| COT Positioning | None | High |
| Credit Spreads | Medium | High |
| Technical (ALMA) | Medium | High |

## Update Schedule

| Time (ET) | Action |
|-----------|--------|
| 06:00-07:00 | Pre-market update |
| Major News | Immediate update if conditions change |
| Sunday Evening | Weekly reset for Globex IB |

## Raw URLs for EA

| File | URL |
|------|-----|
| Bias JSON | `https://raw.githubusercontent.com/joenathanthompson-arch/matrix-nano-reports/main/data/bias_scores/latest.json` |
| Executive Summary | `https://raw.githubusercontent.com/joenathanthompson-arch/matrix-nano-reports/main/data/executive_summaries/latest.md` |

## For Manus AI

See the `docs/` folder:
- `BOOTSTRAP_PROMPT.md` - Copy this into Manus (<5000 chars)
- `MANUS_INSTRUCTIONS.md` - Full methodology and format spec

**Critical:** Both intraday AND swing scores must be provided for each asset class.

---

*Matrix Nano Reports - Manus AI Output v2.1*
