# Manus AI Bias Report Format Specification - Matrix Nano

**Last Updated:** February 22, 2026
**Version:** 1.0

## Overview

Matrix Nano is a **simplified** version of Matrix Futures. Instead of scoring 10 individual symbols, Manus provides:

1. **Overall Market Bias** - General risk-on/risk-off sentiment
2. **Asset Class Biases** - INDICES, COMMODITIES, FX

The Matrix Nano EA then combines your macro bias with real-time technical indicators:
- **ALMA** (Arnaud Legoux Moving Average) - Trend direction
- **MACD** - Momentum confirmation

### Bias Combination Formula

```
Symbol Bias = (Overall x 0.25) + (Asset Class x 0.35) + (ALMA x 0.25) + (MACD x 0.15)
```

This means your macro assessment accounts for 60% of the final bias, while technicals provide 40%.

---

## Required File Structure

```
matrix-nano-reports/
├── data/
│   ├── bias_scores/
│   │   ├── 2026-02-22_0730.json    <- Timestamped copy
│   │   └── latest.json              <- EA READS THIS (CRITICAL!)
│   └── executive_summaries/
│       ├── 2026-02-22_0730.md      <- Timestamped copy
│       └── latest.md               <- /bias command reads this
└── docs/
    ├── BOOTSTRAP_PROMPT.md         <- Your entry prompt
    └── MANUS_INSTRUCTIONS.md       <- This file
```

---

## 1. CRITICAL: `latest.json` Format

**Path:** `data/bias_scores/latest.json`

```json
{
  "date": "2026-02-22",
  "generated_at": "2026-02-22T07:30:00Z",
  "methodology_version": "1.0_NANO",
  "overall": {
    "score": 2,
    "signal": "SLIGHT_BULLISH",
    "confidence": 6,
    "reason": "Risk-on sentiment with low VIX and dovish Fed"
  },
  "asset_classes": {
    "INDICES": {
      "score": 3,
      "signal": "BULLISH",
      "confidence": 7,
      "reason": "Tech earnings strong, credit spreads narrowing"
    },
    "COMMODITIES": {
      "score": 4,
      "signal": "BULLISH",
      "confidence": 7,
      "reason": "Weak USD, supply constraints, gold bid on rate outlook"
    },
    "FX": {
      "score": 0,
      "signal": "NEUTRAL",
      "confidence": 5,
      "reason": "Mixed central bank signals, wait for clarity"
    }
  },
  "key_drivers": [
    "Fed maintaining dovish stance, March cut probability rising",
    "USD weakness supporting commodities and risk assets",
    "Credit spreads stable, no stress signals"
  ],
  "data_quality": {
    "stale_sources": [],
    "fallbacks_used": [],
    "notes": ""
  }
}
```

### Field Requirements

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `date` | string | YES | YYYY-MM-DD |
| `generated_at` | string | YES | ISO 8601 UTC (ends with Z) |
| `methodology_version` | string | YES | "1.0_NANO" |
| `overall` | object | YES | Overall market bias |
| `overall.score` | integer | YES | -10 to +10 (INTEGER) |
| `overall.signal` | string | YES | See signal mapping |
| `overall.confidence` | integer | YES | 1-10 |
| `overall.reason` | string | YES | Brief explanation |
| `asset_classes` | object | YES | Contains INDICES, COMMODITIES, FX |
| `asset_classes.[CLASS].score` | integer | YES | -10 to +10 |
| `asset_classes.[CLASS].signal` | string | YES | See signal mapping |
| `asset_classes.[CLASS].confidence` | integer | YES | 1-10 |
| `asset_classes.[CLASS].reason` | string | YES | Brief explanation |
| `key_drivers` | array | YES | 3-5 string items |
| `data_quality` | object | NO | Optional tracking |

### Signal Mapping (MUST USE EXACTLY)

| Score Range | Signal String |
|-------------|---------------|
| +7 to +10 | `STRONG_BULLISH` |
| +4 to +6 | `BULLISH` |
| +1 to +3 | `SLIGHT_BULLISH` |
| 0 | `NEUTRAL` |
| -1 to -3 | `SLIGHT_BEARISH` |
| -4 to -6 | `BEARISH` |
| -7 to -10 | `STRONG_BEARISH` |

### Required Asset Classes

| Asset Class | Symbols It Affects |
|-------------|-------------------|
| `INDICES` | ES, NQ, YM, RTY |
| `COMMODITIES` | GC, SI, CL |
| `FX` | 6E, 6A, 6J, M6E |

---

## 2. Scoring Methodology

### Overall Market Bias

Assess the general risk appetite in markets:

| Factor | Bearish (-) | Neutral (0) | Bullish (+) |
|--------|-------------|-------------|-------------|
| Fed Stance | Hawkish hike (-2) | Neutral hold (0) | Dovish/cut (+2) |
| VIX Level | >25 (-2) | 15-25 (0) | <15 (+2) |
| Credit Spreads | Widening (-2) | Stable (0) | Narrowing (+2) |
| Growth Outlook | Slowing (-1) | Stable (0) | Accelerating (+1) |
| Risk Sentiment | Risk-off (-1) | Mixed (0) | Risk-on (+1) |

Sum the factors to get Overall score (-10 to +10).

### INDICES Bias

| Factor | Impact |
|--------|--------|
| Real Yields | Falling (+2), Rising (-2) |
| Credit Conditions | Narrowing (+1), Widening (-1) |
| Earnings Outlook | Strong (+1), Weak (-1) |
| VIX Direction | Falling (+1), Rising (-1) |
| Growth | Accelerating (+1), Slowing (-1) |

### COMMODITIES Bias

| Factor | Impact |
|--------|--------|
| USD Direction | Weak (+2), Strong (-2) |
| Real Yields | Falling (+2), Rising (-2) - especially for metals |
| Supply Factors | Tight (+1), Loose (-1) |
| Geopolitical Risk | Rising (+1), Easing (-1) |
| China Demand | Strong (+1), Weak (-1) |

### FX Bias

| Factor | Impact |
|--------|--------|
| Rate Differentials | Widening vs USD (+1), Narrowing (-1) |
| Central Bank Divergence | Hawkish foreign CB (+1), Dovish (-1) |
| Risk Sentiment | Risk-on helps AUD (+1), Risk-off helps JPY |
| USD Trend | Weak USD (+1), Strong USD (-1) |

**FX Notes:**
- 6E (Euro): Bullish = EUR up = USD down
- 6A (AUD): Bullish = AUD up = risk-on currency
- 6J (JPY): Bullish = JPY up = safe-haven bid (INVERTED quotes)
- M6E: Same as 6E

---

## 3. Confidence Scoring

Rate confidence 1-10 based on:

| Confidence | Meaning |
|------------|---------|
| 8-10 | High conviction, fresh data, clear signals |
| 6-7 | Moderate conviction, some uncertainty |
| 4-5 | Low conviction, conflicting signals |
| 1-3 | Very uncertain, consider NO_TRADE |

**Confidence affects position sizing:**
- Confidence 1 = 0.5x size
- Confidence 5 = 1.0x size
- Confidence 10 = 1.5x size

---

## 4. Executive Summary Format

**Path:** `data/executive_summaries/latest.md`

```markdown
# Matrix Nano Daily Bias Report
**Date:** February 22, 2026 | **Time:** 07:30 EST

---

## Overall Market Bias: SLIGHT_BULLISH (+2)
**Confidence:** 6/10

Risk-on sentiment prevails with VIX at low levels and the Fed maintaining a dovish stance. Credit spreads remain stable with no stress signals.

---

## Asset Class Summary

| Asset Class | Score | Signal | Confidence |
|-------------|-------|--------|------------|
| INDICES | +3 | BULLISH | 7/10 |
| COMMODITIES | +4 | BULLISH | 7/10 |
| FX | 0 | NEUTRAL | 5/10 |

---

## INDICES: +3 BULLISH (7/10)

Strong tech earnings continue to support equity indices. Credit spreads are narrowing, indicating healthy risk appetite. Real yields remain contained, providing tailwinds for growth stocks. The setup favors IB_BREAKOUT strategies on long signals.

## COMMODITIES: +4 BULLISH (7/10)

Weak USD is the primary driver for commodities. Gold benefits from falling real yields and safe-haven flows amid geopolitical uncertainty. Energy markets remain supported by supply constraints. Silver follows gold with added industrial demand component.

## FX: NEUTRAL (5/10)

Central bank divergence is unclear. Fed is dovish but ECB and BoJ are sending mixed signals. Wait for clearer direction before establishing directional FX bias. Consider RANGE_TRADE approaches.

---

## Key Macro Themes

1. **Fed Dovish Stance:** March cut probability rising, supports risk assets
2. **USD Weakness:** Benefits commodities and foreign currencies
3. **Credit Stability:** No stress signals, supports equity markets

---

## Upcoming Catalysts

### Imminent (< 1 Week)
- FOMC Minutes (Wed)
- Core PCE (Fri)

### Near-Term (1-4 Weeks)
- NFP Report (Mar 7)
- CPI (Mar 12)

---

## Data Quality
- All data sources current as of February 22, 2026
- No stale data used
- Average confidence: 6.3/10

---
**End of Report**
```

---

## 5. CRITICAL Rules

1. **ALWAYS create both:**
   - `data/bias_scores/latest.json` <- EA reads this!
   - `data/executive_summaries/latest.md` <- /bias command reads this!

2. **Also create timestamped copies:**
   - `data/bias_scores/2026-02-22_0730.json`
   - `data/executive_summaries/2026-02-22_0730.md`

3. **Integer scores only** - No decimals (use +5 not +5.0)

4. **Score != Confidence:**
   - Score = direction/magnitude (-10 to +10)
   - Confidence = certainty of assessment (1-10)

5. **All 3 asset classes required** - INDICES, COMMODITIES, FX

6. **Signal strings must match exactly** - EA parses these

---

## 6. Common Mistakes to Avoid

| Wrong | Correct |
|-------|---------|
| Per-symbol scores like Matrix Futures | Overall + 3 Asset Classes only |
| Score as float (5.0) | Score as integer (5) |
| Missing asset classes | All 3 required: INDICES, COMMODITIES, FX |
| Old CSV format | Use JSON format |
| Forgetting `latest.json` | ALWAYS copy to `latest.json` |

---

## 7. Verification Checklist

Before committing, verify:

- [ ] `data/bias_scores/latest.json` exists and is valid JSON
- [ ] JSON has `overall` with score, signal, confidence, reason
- [ ] JSON has all 3 asset classes (INDICES, COMMODITIES, FX)
- [ ] All scores are integers (-10 to +10)
- [ ] Signal strings match exactly (STRONG_BULLISH, BULLISH, etc.)
- [ ] `data/executive_summaries/latest.md` exists
- [ ] Timestamped copies created for both files
- [ ] `key_drivers` array has 3-5 items

---

## 8. POST-COMMIT VERIFICATION (REQUIRED)

**After EVERY report generation, Manus MUST verify:**

### Verification Steps:

1. **Fetch and validate `latest.json`:**
   ```
   Fetch: https://raw.githubusercontent.com/joenathanthompson-arch/matrix-nano-reports/main/data/bias_scores/latest.json
   ```

   Verify:
   - Valid JSON (no parse errors)
   - Contains `overall` object with score, signal, confidence
   - Contains `asset_classes` object with INDICES, COMMODITIES, FX
   - `date` matches today's date
   - `generated_at` matches your output time

2. **Fetch and validate `latest.md`:**
   ```
   Fetch: https://raw.githubusercontent.com/joenathanthompson-arch/matrix-nano-reports/main/data/executive_summaries/latest.md
   ```

   Verify:
   - File exists and is not empty
   - Contains proper markdown formatting
   - Date in header matches today

### If Verification Fails:
1. DO NOT report success
2. Fix the format issues
3. Commit corrected files
4. Re-run verification
5. Only report success after verification passes

---

## 9. Data Sources Reference

### Fed & Rates
- FedWatch: https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html
- FRED DFII10: https://fred.stlouisfed.org/series/DFII10
- CNBC 10Y TIPS: https://www.cnbc.com/quotes/US10YTIP

### Credit & Volatility
- FRED HY OAS: https://fred.stlouisfed.org/series/BAMLH0A0HYM2
- VIX: https://www.cboe.com/tradable-products/vix/

### Growth & Economic
- GDPNow: https://www.atlantafed.org/cqer/research/gdpnow
- FRED 2s10s: https://fred.stlouisfed.org/series/T10Y2Y

### Currency
- DXY: https://www.tradingview.com/symbols/TVC-DXY/
- ECB: https://www.ecb.europa.eu/press/pr/date/html/index.en.html
- BoJ: https://www.boj.or.jp/en/mopo/index.htm

---

## 10. URLs Reference

| Purpose | URL |
|---------|-----|
| Bias JSON (EA reads) | `https://raw.githubusercontent.com/joenathanthompson-arch/matrix-nano-reports/main/data/bias_scores/latest.json` |
| Executive Summary | `https://raw.githubusercontent.com/joenathanthompson-arch/matrix-nano-reports/main/data/executive_summaries/latest.md` |
| Repository | `https://github.com/joenathanthompson-arch/matrix-nano-reports` |

---

## 11. Difference from Matrix Futures

| Aspect | Matrix Futures | Matrix Nano |
|--------|---------------|-------------|
| Symbols Scored | 10 individual | 0 (asset class level) |
| Output Structure | Per-symbol scores | Overall + 3 Asset Classes |
| Strategy Recs | Per-symbol in JSON | None (EA decides) |
| Technical Integration | PM combines separately | EA combines ALMA + MACD |
| Complexity | High | Simplified |

Matrix Nano is designed to be a lighter-weight system where:
- Manus provides high-level macro direction
- The EA handles per-symbol calculations using technical indicators
- Less data for Manus to produce, faster updates possible
