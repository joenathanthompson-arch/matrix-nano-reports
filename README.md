# Matrix Nano Reports

Manus AI bias data for the Matrix Nano trading system.

## Files

| File | Description |
|------|-------------|
| `MANUS_BIAS.csv` | Daily market bias (Overall + Asset Classes) |

## MANUS_BIAS.csv Format

```csv
TYPE,ID,SCORE,SIGNAL,CONFIDENCE,UPDATED,REASON
MARKET,OVERALL,+2,SLIGHT_BULLISH,6,2026-02-20 07:30,Risk-on VIX low Fed dovish
ASSET_CLASS,INDICES,+3,BULLISH,7,2026-02-20 07:30,Tech earnings strong
ASSET_CLASS,COMMODITIES,+4,BULLISH,7,2026-02-20 07:30,Weak USD gold bid
ASSET_CLASS,FX,0,NEUTRAL,5,2026-02-20 07:30,Mixed signals wait for data
```

### Fields

| Field | Values | Description |
|-------|--------|-------------|
| TYPE | MARKET, ASSET_CLASS | Category of bias |
| ID | OVERALL, INDICES, COMMODITIES, FX | Specific identifier |
| SCORE | -10 to +10 | Bias strength (integer) |
| SIGNAL | See below | Text label matching score |
| CONFIDENCE | 1-10 | Certainty level (affects position sizing) |
| UPDATED | YYYY-MM-DD HH:MM | Timestamp |
| REASON | Text | Brief explanation |

### Signal Values

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

The EA fetches this file from GitHub and combines it with technical indicators:

```
Symbol Bias = (Overall × 0.25) + (Asset Class × 0.35) + (ALMA × 0.25) + (MACD × 0.15)
```

### Asset Class Mapping

| Asset Class | Symbols |
|-------------|---------|
| INDICES | ES, NQ, YM, RTY |
| COMMODITIES | GC, SI, CL |
| FX | 6E, 6A, 6J, M6E |

### Confidence → Position Sizing

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

## Raw URL for EA

```
https://raw.githubusercontent.com/joenathanthompson-arch/matrix-nano-reports/main/MANUS_BIAS.csv
```

---

*Matrix Nano Reports - Manus AI Output*
