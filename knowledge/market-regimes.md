# Market Regime Classification

## Regime 1: Strong Trend
**Conditions:**
- ADX > 30
- Price cleanly above/below 50 EMA on 4H
- Higher timeframe (daily) aligned with trade direction
- Volume confirms moves

**Strategy:** Trend continuation setups only. Full position size allowed.

## Regime 2: Weak Trend / Transition
**Conditions:**
- ADX 20–30
- Price near or interacting with key EMAs
- Mixed signals across timeframes
- Unclear higher timeframe direction

**Strategy:** Reduce position size 50%. Only take setups with 4+ confluence factors. Avoid aggressive entries.

## Regime 3: Range
**Conditions:**
- ADX < 20
- Price oscillating between clearly defined support and resistance
- No directional momentum

**Strategy:** Fade extremes at defined boundaries only. Tight stops. Prefer to stand aside.

## Regime 4: High Volatility / Expansion
**Conditions:**
- ATR > 2x its 20-period average
- Usually pre/post major news events
- Erratic price movement, wide candles

**Strategy:** Stand aside. Do not trade. Wait for regime normalization.

## Regime Detection Algorithm
1. Calculate ADX(14) on 4H timeframe
2. Calculate ATR ratio: current ATR(14) / 20-period SMA of ATR(14)
3. Check EMA alignment: 20/50/200 on both 1H and 4H
4. Determine price position relative to key EMAs
5. Cross-reference with daily trend structure (HH/HL or LH/LL)
6. Classify regime and apply corresponding risk rules

## Regime Transition Rules
- Wait for 3 consecutive candles (on primary timeframe) to confirm regime change
- Do not chase a trade after a regime shift — wait for first clean setup in new regime
- Log regime changes in journal
