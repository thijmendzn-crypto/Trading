# Strategy Framework

## Core Philosophy
- Only trade when minimum 3 confluence factors align
- Risk/reward minimum: 2.5:1 for day trades, 3:1 for swing trades
- Maximum 2% portfolio risk per trade
- Never average into a losing position
- Wait for confirmation before entry — not anticipation
- No trade is always better than a bad trade
- Consistency beats occasional big wins

## Valid Setup Types

### Type 1: Trend Continuation Pullback
- Price in clear trend (ADX > 25)
- Pullback to structure level (EMA, order block, or FVG)
- Momentum divergence or loss of bearish/bullish momentum on lower TF
- Entry on confirmation candle

### Type 2: Liquidity Grab + Reversal
- Price sweeps a clear swing high/low (stop hunt)
- Immediate rejection candle
- Entry after close of rejection candle
- Stop beyond the wick

### Type 3: Breakout + Retest
- Clean level broken with volume
- Price retests broken level
- Entry on retest confirmation
- Volume must confirm (>1.2x average)

### Type 4: Fair Value Gap Fill
- FVG identified in trending market
- Price pulls back into FVG
- Entry at 50% of FVG
- Only in direction of higher timeframe trend

## Invalid Setups (Auto-Reject)
- Counter-trend trade in strong momentum market (ADX > 35)
- Any setup without clear stop placement
- Choppy/ranging market without clear structure boundary
- Within 30 minutes of high-impact news event
- Volume below 0.7x 20-period average
- R/R below 2.5:1
- Fewer than 3 confluence factors
- High volatility regime (ATR > 2x average)

## Position Sizing Rules
- Risk 1% per trade baseline
- Max 2% for A+ setups (confidence > 0.80, score > 85)
- Reduce to 0.5% in weak trend / transitioning regime
- Never risk more than 4% total open exposure

## Trade Management
- TP1 at 1.5R — move stop to breakeven
- TP2 at 2.5R — take partial profit
- Let runner to TP3 if structure allows
- Never move stop against the trade
