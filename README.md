# Matrix Nano Reports

Manus AI bias data for the Matrix Nano trading system.

## Overview

Matrix Nano uses a **simplified bias system** compared to Matrix Futures:
- **1 Overall Market Bias** - General risk-on/risk-off sentiment
- **3 Asset Class Biases** - INDICES, COMMODITIES, FX

The EA combines Manus bias with technical indicators (ALMA + MACD) to calculate per-symbol scores.

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

## latest.json Format

```json
{
  "date": "2026-02-22",
  "generated_at": "2026-02-22T07:30:00Z",
  "methodology_version": "1.0_NANO",
  "overall": {
    "score": 2,
    "signal": "SLIGHT_BULLISH",
    "confidence": 6,
    "reason": "Risk-on VIX low Fed dovish"
  },
  "asset_classes": {
    "INDICES": {
      "score": 3,
      "signal": "BULLISH",
      "confidence": 7,
      "reason": "Tech earnings strong"
    },
    "COMMODITIES": {
      "score": 4,
      "signal": "BULLISH",
      "confidence": 7,
      "reason": "Weak USD gold bid"
    },
    "FX": {
      "score": 0,
      "signal": "NEUTRAL",
      "confidence": 5,
      "reason": "Mixed signals"
    }
  },
  "key_drivers": [
    "Fed dovish stance",
    "USD weakness",
    "Credit stability"
  ],
  "data_quality": {
    "stale_sources": [],
    "fallbacks_used": []
  }
}
```

## Fields

### Overall Market Bias

| Field | Type | Description |
|-------|------|-------------|
| score | integer | -10 to +10 |
| signal | string | STRONG_BULLISH, BULLISH, SLIGHT_BULLISH, NEUTRAL, SLIGHT_BEARISH, BEARISH, STRONG_BEARISH |
| confidence | integer | 1-10 (affects position sizing) |
| reason | string | Brief explanation |

### Asset Class Biases

Same fields as overall, for each of:
- **INDICES** (ES, NQ, YM, RTY)
- **COMMODITIES** (GC, SI, CL)
- **FX** (6E, 6A, 6J, M6E)

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

### Asset Class Mapping

| Asset Class | Symbols |
|-------------|---------|
| INDICES | ES, NQ, YM, RTY |
| COMMODITIES | GC, SI, CL |
| FX | 6E, 6A, 6J, M6E |

### Confidence -> Position Sizing

| Confidence | Size Multiplier |
|------------|-----------------|
| 1 | 0.5x |
| 5 | 1.0x |
| 10 | 1.5x |

## Update Schedule

| Time (ET) | Action |
|-----------|--------|
| 06:00-07:00 | Pre-market update |
| Major News | Immediate update if conditions change |

## Raw URLs for EA

| File | URL |
|------|-----|
| Bias JSON | `https://raw.githubusercontent.com/joenathanthompson-arch/matrix-nano-reports/main/data/bias_scores/latest.json` |
| Executive Summary | `https://raw.githubusercontent.com/joenathanthompson-arch/matrix-nano-reports/main/data/executive_summaries/latest.md` |

## For Manus AI

See the `docs/` folder:
- `BOOTSTRAP_PROMPT.md` - Copy this into Manus (<5000 chars)
- `MANUS_INSTRUCTIONS.md` - Full methodology and format spec

---

*Matrix Nano Reports - Manus AI Output*
