# Risk Management

## Core Risk Rules — Non-Negotiable

### Per-Trade Risk
- Default: 1% of portfolio per trade
- A+ setup (score > 85, confidence > 0.80): max 2%
- Weak regime or low confidence: 0.5%
- Absolute maximum open exposure: 4% across all trades

### Daily Loss Limit
- Stop trading after losing 3% in a single day
- Take a 24-hour break before returning
- Review all trades before resuming

### Weekly Loss Limit
- If down 6% in a week, reduce position size by 50% for next week
- If down 10% in a week, stop trading for remainder of week

### Drawdown Rules
- If portfolio down 10% from peak: reduce all position sizes by 50%
- If portfolio down 15% from peak: stop trading, review system
- If portfolio down 20% from peak: full system review before resuming

## Stop Loss Placement
- Always placed at a logical level (beyond structure, not arbitrary distance)
- Never place stop inside a consolidation zone
- Minimum stop size: 0.5 ATR to avoid noise stop-outs
- Stop must be placed BEFORE calculating position size

## Position Size Formula
```
Position Size = (Portfolio Value × Risk %) / (Entry Price - Stop Loss Price)
```

Example:
- Portfolio: $10,000
- Risk: 1% = $100
- Entry: $50,000
- Stop: $49,500 (gap = $500)
- Position Size = $100 / $500 = 0.2 units

## Risk/Reward Requirements
- Minimum R/R: 2.5:1 for all trades
- Target R/R: 3:1 or better
- A+ setups: 4:1 or better preferred
- Never take a trade with R/R below 2:1 regardless of confidence

## Correlated Positions
- Do not hold BTC and ETH longs simultaneously at full size (0.7+ correlation)
- If taking correlated trades, reduce each to 0.5% risk
- Maximum 2 correlated positions at any time

## Emergency Protocols
- Exchange/broker outage: pre-set stops always active
- Internet outage: mobile backup always configured
- All positions must have hard stops set immediately after entry
