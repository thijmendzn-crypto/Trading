"""
Market structure analysis: swing points, HH/HL/LH/LL, BOS, order blocks, FVGs.
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass


@dataclass
class SwingPoint:
    index: int
    time: pd.Timestamp
    price: float
    kind: str  # 'high' or 'low'


@dataclass
class OrderBlock:
    direction: str  # 'bullish' or 'bearish'
    top: float
    bottom: float
    time: pd.Timestamp
    valid: bool = True


@dataclass
class FairValueGap:
    direction: str  # 'bullish' or 'bearish'
    top: float
    bottom: float
    midpoint: float
    time: pd.Timestamp
    filled: bool = False


def find_swing_points(df: pd.DataFrame, lookback: int = 3) -> list[SwingPoint]:
    """Identify swing highs and lows using a rolling window."""
    swings = []
    highs = df["high"].values
    lows = df["low"].values
    times = df.index

    for i in range(lookback, len(df) - lookback):
        window_highs = highs[i - lookback:i + lookback + 1]
        window_lows = lows[i - lookback:i + lookback + 1]

        if highs[i] == window_highs.max():
            swings.append(SwingPoint(i, times[i], highs[i], "high"))

        if lows[i] == window_lows.min():
            swings.append(SwingPoint(i, times[i], lows[i], "low"))

    return swings


def classify_structure(swings: list[SwingPoint]) -> str:
    """
    Classify market structure as HH_HL (bullish), LH_LL (bearish), or NEUTRAL.
    Requires at least 4 swing points.
    """
    if len(swings) < 4:
        return "NEUTRAL"

    highs = [s for s in swings if s.kind == "high"][-2:]
    lows = [s for s in swings if s.kind == "low"][-2:]

    if len(highs) < 2 or len(lows) < 2:
        return "NEUTRAL"

    hh = highs[-1].price > highs[-2].price
    hl = lows[-1].price > lows[-2].price
    lh = highs[-1].price < highs[-2].price
    ll = lows[-1].price < lows[-2].price

    if hh and hl:
        return "HH_HL"  # Bullish
    if lh and ll:
        return "LH_LL"  # Bearish
    return "NEUTRAL"


def find_key_levels(df: pd.DataFrame, swings: list[SwingPoint]) -> tuple[list[float], list[float]]:
    """Extract support and resistance levels from swing points."""
    current_price = df["close"].iloc[-1]
    tolerance = current_price * 0.002  # 0.2% tolerance for clustering

    raw_highs = [s.price for s in swings if s.kind == "high"]
    raw_lows = [s.price for s in swings if s.kind == "low"]

    def cluster_levels(levels: list[float]) -> list[float]:
        if not levels:
            return []
        sorted_levels = sorted(levels)
        clustered = [sorted_levels[0]]
        for level in sorted_levels[1:]:
            if abs(level - clustered[-1]) > tolerance:
                clustered.append(level)
            else:
                clustered[-1] = (clustered[-1] + level) / 2  # Average
        return clustered

    resistance = [l for l in cluster_levels(raw_highs) if l > current_price][-5:]
    support = [l for l in cluster_levels(raw_lows) if l < current_price][-5:]

    return sorted(support), sorted(resistance)


def find_order_blocks(df: pd.DataFrame, swings: list[SwingPoint]) -> list[OrderBlock]:
    """
    Find order blocks: the last candle before a significant move
    that broke structure.
    """
    blocks = []
    closes = df["close"].values
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    times = df.index

    for i in range(1, len(df) - 1):
        # Bullish OB: last down-candle before a strong up-move
        if closes[i] < opens[i]:  # Bearish candle
            if i + 3 < len(df):
                next_move = (closes[i + 3] - closes[i]) / closes[i]
                if next_move > 0.005:  # >0.5% move up
                    blocks.append(OrderBlock(
                        direction="bullish",
                        top=max(opens[i], closes[i]),
                        bottom=min(opens[i], closes[i]),
                        time=times[i],
                    ))

        # Bearish OB: last up-candle before a strong down-move
        if closes[i] > opens[i]:  # Bullish candle
            if i + 3 < len(df):
                next_move = (closes[i + 3] - closes[i]) / closes[i]
                if next_move < -0.005:  # >0.5% move down
                    blocks.append(OrderBlock(
                        direction="bearish",
                        top=max(opens[i], closes[i]),
                        bottom=min(opens[i], closes[i]),
                        time=times[i],
                    ))

    # Only keep the 3 most recent of each type
    bullish = [b for b in blocks if b.direction == "bullish"][-3:]
    bearish = [b for b in blocks if b.direction == "bearish"][-3:]

    return bullish + bearish


def find_fair_value_gaps(df: pd.DataFrame) -> list[FairValueGap]:
    """
    Find Fair Value Gaps: 3-candle patterns where candle 1 wick
    and candle 3 wick do not overlap.
    """
    gaps = []
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    times = df.index

    for i in range(1, len(df) - 1):
        # Bullish FVG: candle 1 high < candle 3 low
        if highs[i - 1] < lows[i + 1]:
            gap_bottom = highs[i - 1]
            gap_top = lows[i + 1]
            gaps.append(FairValueGap(
                direction="bullish",
                top=gap_top,
                bottom=gap_bottom,
                midpoint=(gap_top + gap_bottom) / 2,
                time=times[i],
            ))

        # Bearish FVG: candle 1 low > candle 3 high
        if lows[i - 1] > highs[i + 1]:
            gap_top = lows[i - 1]
            gap_bottom = highs[i + 1]
            gaps.append(FairValueGap(
                direction="bearish",
                top=gap_top,
                bottom=gap_bottom,
                midpoint=(gap_top + gap_bottom) / 2,
                time=times[i],
            ))

    # Mark filled gaps
    current_price = closes[-1]
    for gap in gaps:
        if gap.direction == "bullish" and current_price > gap.top:
            gap.filled = True
        if gap.direction == "bearish" and current_price < gap.bottom:
            gap.filled = True

    # Return only unfilled recent gaps
    return [g for g in gaps[-10:] if not g.filled]
