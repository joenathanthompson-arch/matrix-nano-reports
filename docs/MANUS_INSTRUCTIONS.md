# Manus AI Bias Report Format Specification - Matrix Nano

**Last Updated:** February 22, 2026
**Version:** 2.0

## Overview

Matrix Nano is a **simplified** version of Matrix Futures. Instead of scoring individual symbols, Manus provides:

1. **Overall Market Bias** - General risk-on/risk-off sentiment
2. **8 Asset Class Biases** - Granular coverage across all major futures markets

The Matrix Nano EA then combines your macro bias with real-time technical indicators:
- **ALMA** (Arnaud Legoux Moving Average) - Trend direction
- **MACD** - Momentum confirmation

### Bias Combination Formula

```
Symbol Bias = (Overall x 0.25) + (Asset Class x 0.35) + (ALMA x 0.25) + (MACD x 0.15)
```

This means your macro assessment accounts for 60% of the final bias, while technicals provide 40%.

---

## The 8 Asset Classes

| Asset Class | ID | Key Symbols | Description |
|-------------|-----|-------------|-------------|
| Equity Index Futures | `EQUITY_INDEX` | ES, NQ, YM, RTY, MES, MNQ | Stock market indices |
| Interest Rate/Fixed Income | `FIXED_INCOME` | ZB, ZN, ZT, ZF, GE, SR3 | Government debt instruments |
| Energy Futures | `ENERGY` | CL, NG, RB, HO, MCL, QG | Oil, gas, refined products |
| Metal Futures | `METALS` | GC, SI, HG, PL, PA, MGC | Precious & industrial metals |
| Agricultural Futures | `AGRICULTURE` | ZC, ZS, ZW, KC, SB, CC, LE, HE | Grains, softs, livestock |
| Currency Futures | `FX` | 6E, 6J, 6A, 6B, 6C, 6S, M6E | Foreign exchange |
| Cryptocurrency Futures | `CRYPTO` | BTC, ETH, MBT | Digital assets |
| Volatility Index Futures | `VOLATILITY` | VX, VXM | VIX-based contracts |

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
  "methodology_version": "2.0_NANO",
  "overall": {
    "score": 2,
    "signal": "SLIGHT_BULLISH",
    "confidence": 6,
    "reason": "Risk-on sentiment with low VIX and dovish Fed"
  },
  "asset_classes": {
    "EQUITY_INDEX": {
      "score": 3,
      "signal": "BULLISH",
      "confidence": 7,
      "reason": "Tech earnings strong, credit spreads narrowing"
    },
    "FIXED_INCOME": {
      "score": -2,
      "signal": "SLIGHT_BEARISH",
      "confidence": 6,
      "reason": "Fed dovish but inflation sticky, curve steepening"
    },
    "ENERGY": {
      "score": 2,
      "signal": "SLIGHT_BULLISH",
      "confidence": 5,
      "reason": "Supply constraints, weak USD, demand stable"
    },
    "METALS": {
      "score": 4,
      "signal": "BULLISH",
      "confidence": 7,
      "reason": "Falling real yields, weak USD, safe-haven bid"
    },
    "AGRICULTURE": {
      "score": 1,
      "signal": "SLIGHT_BULLISH",
      "confidence": 5,
      "reason": "Weather concerns, weak USD support"
    },
    "FX": {
      "score": 0,
      "signal": "NEUTRAL",
      "confidence": 5,
      "reason": "Mixed central bank signals, wait for clarity"
    },
    "CRYPTO": {
      "score": 3,
      "signal": "BULLISH",
      "confidence": 6,
      "reason": "Risk-on sentiment, ETF inflows, halving anticipation"
    },
    "VOLATILITY": {
      "score": -1,
      "signal": "SLIGHT_BEARISH",
      "confidence": 6,
      "reason": "VIX subdued, low vol regime, sell premium environment"
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
| `methodology_version` | string | YES | "2.0_NANO" |
| `overall` | object | YES | Overall market bias |
| `overall.score` | integer | YES | -10 to +10 (INTEGER) |
| `overall.signal` | string | YES | See signal mapping |
| `overall.confidence` | integer | YES | 1-10 |
| `overall.reason` | string | YES | Brief explanation |
| `asset_classes` | object | YES | Contains all 8 asset classes |
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

### Required Asset Class IDs (All 8 Required)

```
EQUITY_INDEX, FIXED_INCOME, ENERGY, METALS, AGRICULTURE, FX, CRYPTO, VOLATILITY
```

---

## 2. Scoring Methodology by Asset Class

### Overall Market Bias

Assess the general risk appetite in markets:

| Factor | Bearish (-) | Neutral (0) | Bullish (+) |
|--------|-------------|-------------|-------------|
| Fed Stance | Hawkish hike (-2) | Neutral hold (0) | Dovish/cut (+2) |
| VIX Level | >25 (-2) | 15-25 (0) | <15 (+2) |
| Credit Spreads | Widening (-2) | Stable (0) | Narrowing (+2) |
| Growth Outlook | Slowing (-1) | Stable (0) | Accelerating (+1) |
| Risk Sentiment | Risk-off (-1) | Mixed (0) | Risk-on (+1) |

---

### EQUITY_INDEX Bias

**Symbols:** ES, NQ, YM, RTY, MES, MNQ, MYM, M2K

| Factor | Weight | Source | Impact |
|--------|--------|--------|--------|
| Fed Stance | 1x | FedWatch | Dovish (+), Hawkish (-) |
| Real Yields | 2x | DFII10 | Falling (+), Rising (-) |
| Credit Spreads | 1x | HY OAS | Narrowing (+), Widening (-) |
| VIX Direction | 1x | CBOE | Falling (+), Rising (-) |
| Earnings | 1x | News | Beats (+), Misses (-) |
| Growth | 1x | GDPNow | Stable/Up (+), Slowing (-) |

---

### FIXED_INCOME Bias

**Symbols:** ZB (30Y Bond), ZN (10Y Note), ZT (2Y Note), ZF (5Y Note), GE (Eurodollar), SR3 (SOFR)

| Factor | Weight | Source | Impact |
|--------|--------|--------|--------|
| Fed Policy | 2x | FedWatch/FOMC | Dovish (+), Hawkish (-) |
| Inflation Expectations | 2x | TIPS Breakevens | Falling (+), Rising (-) |
| Fiscal/Supply | 1x | Treasury Auctions | Light (+), Heavy (-) |
| Curve Shape | 1x | 2s10s | Flattening (+), Steepening (-) |
| Risk Sentiment | 1x | VIX | Risk-off (+), Risk-on (-) |

**Note:** Bullish FIXED_INCOME = Bond prices UP = Yields DOWN

---

### ENERGY Bias

**Symbols:** CL (WTI Crude), NG (Natural Gas), RB (RBOB Gasoline), HO (Heating Oil), MCL, QG

| Factor | Weight | Source | Impact |
|--------|--------|--------|--------|
| OPEC Policy | 2x | OPEC News | Cuts (+), Increases (-) |
| Inventories | 2x | EIA Weekly | Draws (+), Builds (-) |
| USD Direction | 1x | DXY | Weak (+), Strong (-) |
| Geopolitical | 1x | News | Risk (+), Calm (-) |
| Global Demand | 1x | China PMI | Strong (+), Weak (-) |

---

### METALS Bias

**Symbols:** GC (Gold), SI (Silver), HG (Copper), PL (Platinum), PA (Palladium), MGC, SIL

| Factor | Weight | Source | Impact |
|--------|--------|--------|--------|
| Real Yields | 2x | DFII10 | Falling (+), Rising (-) |
| USD Direction | 2x | DXY | Weak (+), Strong (-) |
| Risk Sentiment | 1x | VIX | Risk-off (+Gold), Risk-on (+Copper) |
| China Demand | 1x | China PMI | Strong (+), Weak (-) |
| ETF Flows | 1x | GLD Holdings | Inflows (+), Outflows (-) |

**Note:** Precious metals (GC, SI) favor risk-off. Industrial metals (HG) favor risk-on.

---

### AGRICULTURE Bias

**Symbols:** ZC (Corn), ZS (Soybeans), ZW (Wheat), ZM (Soybean Meal), ZL (Soybean Oil), KC (Coffee), SB (Sugar), CC (Cocoa), CT (Cotton), LE (Live Cattle), HE (Lean Hogs), GF (Feeder Cattle)

| Factor | Weight | Source | Impact |
|--------|--------|--------|--------|
| Weather | 2x | NOAA/USDA | Adverse (+), Favorable (-) |
| USD Direction | 1x | DXY | Weak (+), Strong (-) |
| Global Demand | 1x | WASDE | Strong (+), Weak (-) |
| Inventory Levels | 1x | USDA | Low (+), High (-) |
| Growing Season | 1x | Seasonal | Planting uncertainty (+) |

**Key Reports:** USDA WASDE (monthly), Crop Progress (weekly), Export Sales (weekly)

---

### FX Bias

**Symbols:** 6E (EUR), 6J (JPY), 6A (AUD), 6B (GBP), 6C (CAD), 6S (CHF), 6N (NZD), M6E, M6A

| Factor | Weight | Source | Impact |
|--------|--------|--------|--------|
| Fed vs Foreign CB | 2x | Central Banks | Foreign hawkish (+), Fed hawkish (-) |
| Rate Differentials | 2x | FRED/CBs | Widening vs USD (+), Narrowing (-) |
| Risk Sentiment | 1x | VIX | Risk-on (+AUD, +NZD), Risk-off (+JPY, +CHF) |
| USD Trend | 1x | DXY | Weak USD (+), Strong USD (-) |

**FX Notes:**
- 6E: Bullish = EUR up = USD down
- 6J: Bullish = JPY up = USD/JPY DOWN (inverted!)
- 6A: Risk currency, tracks China/commodities
- 6B: Brexit/BoE sensitive
- 6C: Oil-linked (CAD correlates with crude)

---

### CRYPTO Bias

**Symbols:** BTC (Bitcoin), ETH (Ethereum), MBT (Micro Bitcoin)

| Factor | Weight | Source | Impact |
|--------|--------|--------|--------|
| Risk Sentiment | 2x | VIX/Equities | Risk-on (+), Risk-off (-) |
| ETF Flows | 2x | Coinglass | Inflows (+), Outflows (-) |
| Regulatory News | 1x | Headlines | Positive (+), Negative (-) |
| On-chain Metrics | 1x | Glassnode | Accumulation (+), Distribution (-) |
| Halving Cycle | 1x | BTC Supply | Pre-halving (+), Post-halving mixed |

**Note:** Crypto is highly correlated to NQ/risk assets. Size appropriately for volatility.

---

### VOLATILITY Bias

**Symbols:** VX (VIX Futures), VXM (Micro VIX)

| Factor | Weight | Source | Impact |
|--------|--------|--------|--------|
| VIX Spot Level | 2x | CBOE | High (+), Low (-) |
| Term Structure | 2x | VIX Curve | Backwardation (+), Contango (-) |
| Event Calendar | 1x | Econ Calendar | Heavy (+), Light (-) |
| Realized Vol | 1x | SPX | Rising (+), Falling (-) |

**IMPORTANT - VOLATILITY BIAS INTERPRETATION:**
- **Bullish VOLATILITY** = Expect VIX to RISE = Long VX
- **Bearish VOLATILITY** = Expect VIX to FALL = Short VX / sell premium
- In calm markets, VOLATILITY bias is typically bearish (contango decay)

---

## 3. Confidence Scoring

Rate confidence 1-10 based on:

| Confidence | Meaning |
|------------|---------|
| 8-10 | High conviction, fresh data, clear signals |
| 6-7 | Moderate conviction, some uncertainty |
| 4-5 | Low conviction, conflicting signals |
| 1-3 | Very uncertain, consider reduced sizing |

**Confidence affects position sizing:**
- Confidence 1 = 0.5x size
- Confidence 5 = 1.0x size
- Confidence 10 = 1.5x size

---

## 4. Data Sources Reference

### Fed & Rates
| Data | Primary | Fallback |
|------|---------|----------|
| FedWatch | cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html | - |
| Real Yields (DFII10) | fred.stlouisfed.org/series/DFII10 | cnbc.com/quotes/US10YTIP |
| 2s10s Curve | fred.stlouisfed.org/series/T10Y2Y | cnbc.com/quotes/10Y2YS |
| HY OAS | fred.stlouisfed.org/series/BAMLH0A0HYM2 | tradingeconomics.com |

### Volatility & Risk
| Data | Source |
|------|--------|
| VIX | cboe.com/tradable-products/vix/ |
| MOVE | tradingview.com/symbols/TVC-MOVE/ |
| VIX Term Structure | vixcentral.com |

### Growth & Economic
| Data | Source |
|------|--------|
| GDPNow | atlantafed.org/cqer/research/gdpnow |
| ISM PMI | ismworld.org |
| Economic Calendar | forexfactory.com/calendar |

### Energy
| Data | Source |
|------|--------|
| EIA Weekly Petroleum | eia.gov/petroleum/supply/weekly/ |
| OPEC Reports | opec.org |
| Natural Gas Storage | eia.gov/naturalgas/storage/ |

### Metals
| Data | Source |
|------|--------|
| Gold ETF Holdings | gold.org/goldhub/data/gold-etfs-holdings-and-flows |
| Copper | investing.com/commodities/copper |
| China PMI | tradingeconomics.com/china/manufacturing-pmi |

### Agriculture
| Data | Source |
|------|--------|
| USDA WASDE | usda.gov/oce/commodity/wasde |
| Crop Progress | usda.gov/nass/publications/crop-progress |
| Weather | noaa.gov |

### FX & Central Banks
| Data | Source |
|------|--------|
| DXY | tradingview.com/symbols/TVC-DXY/ |
| ECB | ecb.europa.eu |
| BoJ | boj.or.jp/en/ |
| BoE | bankofengland.co.uk |
| RBA | rba.gov.au |

### Crypto
| Data | Source |
|------|--------|
| BTC ETF Flows | coinglass.com/bitcoin-etf |
| On-chain Metrics | glassnode.com |
| Fear & Greed | alternative.me/crypto/fear-and-greed-index/ |

---

## 5. Executive Summary Format

**Path:** `data/executive_summaries/latest.md`

```markdown
# Matrix Nano Daily Bias Report
**Date:** February 22, 2026 | **Time:** 07:30 EST

---

## Overall Market Bias: [SIGNAL] ([SCORE])
**Confidence:** X/10

[2-3 sentence summary]

---

## Asset Class Summary

| Asset Class | Score | Signal | Confidence |
|-------------|-------|--------|------------|
| EQUITY_INDEX | +X | SIGNAL | X/10 |
| FIXED_INCOME | +X | SIGNAL | X/10 |
| ENERGY | +X | SIGNAL | X/10 |
| METALS | +X | SIGNAL | X/10 |
| AGRICULTURE | +X | SIGNAL | X/10 |
| FX | +X | SIGNAL | X/10 |
| CRYPTO | +X | SIGNAL | X/10 |
| VOLATILITY | +X | SIGNAL | X/10 |

---

## Detailed Asset Class Analysis

### EQUITY_INDEX: +X SIGNAL (X/10)
**Symbols:** ES, NQ, YM, RTY, MES, MNQ, MYM, M2K

[2-3 sentence analysis]

[Repeat for all 8 asset classes]

---

## Key Macro Themes

1. **[Theme 1]**: [Explanation]
2. **[Theme 2]**: [Explanation]
3. **[Theme 3]**: [Explanation]

---

## Upcoming Catalysts

### Imminent (< 1 Week)
- [Event] (Date)

### Near-Term (1-4 Weeks)
- [Event] (Date)

---

## Data Quality
- All data sources current as of [Date]
- Stale sources: [list or "None"]
- Average confidence: X.X/10

---
**End of Report**
```

---

## 6. CRITICAL Rules

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

5. **All 8 asset classes required** - No partial updates

6. **Signal strings must match exactly** - EA parses these

---

## 7. Symbol Mapping Reference

When the EA loads bias for a symbol, it maps to asset class:

| Symbol Pattern | Asset Class |
|----------------|-------------|
| ES, NQ, YM, RTY, MES, MNQ, MYM, M2K | EQUITY_INDEX |
| ZB, ZN, ZT, ZF, GE, SR3 | FIXED_INCOME |
| CL, NG, RB, HO, MCL, QG | ENERGY |
| GC, SI, HG, PL, PA, MGC, SIL | METALS |
| ZC, ZS, ZW, ZM, ZL, KC, SB, CC, CT, LE, HE, GF | AGRICULTURE |
| 6E, 6J, 6A, 6B, 6C, 6S, 6N, M6E, M6A | FX |
| BTC, ETH, MBT | CRYPTO |
| VX, VXM | VOLATILITY |

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
   - Contains `asset_classes` object with all 8 classes
   - Each class has score, signal, confidence, reason
   - `date` matches today's date
   - `generated_at` matches your output time

2. **Fetch and validate `latest.md`:**
   ```
   Fetch: https://raw.githubusercontent.com/joenathanthompson-arch/matrix-nano-reports/main/data/executive_summaries/latest.md
   ```

3. **If verification fails:** Re-commit and push, then verify again.

---

## 9. Difference from Matrix Futures

| Aspect | Matrix Futures | Matrix Nano |
|--------|---------------|-------------|
| Symbols Scored | 10 individual | 0 (asset class level) |
| Asset Classes | 3 | 8 (more granular) |
| Output Structure | Per-symbol with strategy | Overall + 8 Asset Classes |
| Technical Integration | PM combines separately | EA combines ALMA + MACD |
| Markets Covered | Limited futures | All major futures |
