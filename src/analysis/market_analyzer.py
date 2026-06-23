"""
Main market analysis engine.
Combines all indicators and structure analysis into a MarketSnapshot.
"""
from dataclasses import dataclass, field
import pandas as pd
import numpy as np
from loguru import logger

from .indicators import ema, atr, rsi, adx, vwap, volume_ratio
from .structure import (
    find_swing_points, classify_structure, find_key_levels,
    find_order_blocks, find_fair_value_gaps,
    SwingPoint, OrderBlock, FairValueGap,
)


@dataclass
class MarketSnapshot:
    symbol: str
    timeframe: str
    current_price: float
    timestamp: pd.Timestamp

    # Trend
    trend: str = "NEUTRAL"           # BULLISH / BEARISH / NEUTRAL
    trend_strength: float = 0.0      # 0.0 to 1.0

    # Regime
    regime: str = "RANGING"          # TRENDING / RANGING / VOLATILE

    # Indicators
    adx_value: float = 0.0
    rsi_value: float = 50.0
    atr_value: float = 0.0
    atr_ratio: float = 1.0
    volume_ratio_value: float = 1.0

    # EMAs
    ema_20: float = 0.0
    ema_50: float = 0.0
    ema_200: float = 0.0
    vwap_value: float = 0.0

    # Structure
    market_structure: str = "NEUTRAL"    # HH_HL / LH_LL / NEUTRAL
    key_support: list[float] = field(default_factory=list)
    key_resistance: list[float] = field(default_factory=list)
    order_blocks: list[dict] = field(default_factory=list)
    fair_value_gaps: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "current_price": self.current_price,
            "trend": self.trend,
            "trend_strength": round(self.trend_strength, 2),
            "regime": self.regime,
            "adx": round(self.adx_value, 1),
            "rsi": round(self.rsi_value, 1),
            "atr": round(self.atr_value, 6),
            "atr_ratio": round(self.atr_ratio, 2),
            "volume_ratio": round(self.volume_ratio_value, 2),
            "ema_20": round(self.ema_20, 4),
            "ema_50": round(self.ema_50, 4),
            "ema_200": round(self.ema_200, 4),
            "vwap": round(self.vwap_value, 4),
            "market_structure": self.market_structure,
            "key_support": [round(l, 4) for l in self.key_support],
            "key_resistance": [round(l, 4) for l in self.key_resistance],
            "order_blocks": self.order_blocks,
            "fair_value_gaps": self.fair_value_gaps,
        }


class MarketAnalyzer:

    def analyze(
        self,
        symbol: str,
        df_primary: pd.DataFrame,
        df_higher: pd.DataFrame | None = None,
    ) -> MarketSnapshot:
        """
        Run full market analysis on a symbol.

        Args:
            symbol: Trading pair (e.g. BTCUSDT)
            df_primary: OHLCV DataFrame for primary timeframe (e.g. 1H)
            df_higher: OHLCV DataFrame for higher timeframe (e.g. 4H) for confluence
        """
        if len(df_primary) < 50:
            raise ValueError(f"Insufficient data: {len(df_primary)} candles, need 50+")

        current_price = float(df_primary["close"].iloc[-1])
        timeframe = "1h"  # Default; caller can override

        snapshot = MarketSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            current_price=current_price,
            timestamp=df_primary.index[-1],
        )

        self._calculate_indicators(snapshot, df_primary)
        self._classify_regime(snapshot)
        self._calculate_trend(snapshot, df_primary, df_higher)
        self._calculate_structure(snapshot, df_primary)

        logger.debug(
            f"{symbol} | Price={current_price:.2f} | "
            f"Regime={snapshot.regime} | Trend={snapshot.trend} | "
            f"ADX={snapshot.adx_value:.1f} | RSI={snapshot.rsi_value:.1f}"
        )

        return snapshot

    def _calculate_indicators(self, snapshot: MarketSnapshot, df: pd.DataFrame):
        """Compute all technical indicators."""
        close = df["close"]

        snapshot.ema_20 = float(ema(close, 20).iloc[-1])
        snapshot.ema_50 = float(ema(close, 50).iloc[-1])
        snapshot.ema_200 = float(ema(close, 200).iloc[-1]) if len(df) >= 200 else float(ema(close, len(df)).iloc[-1])

        snapshot.adx_value = float(adx(df, 14).iloc[-1])
        snapshot.rsi_value = float(rsi(close, 14).iloc[-1])

        atr_series = atr(df, 14)
        snapshot.atr_value = float(atr_series.iloc[-1])
        atr_avg = float(atr_series.rolling(20).mean().iloc[-1])
        snapshot.atr_ratio = snapshot.atr_value / atr_avg if atr_avg > 0 else 1.0

        snapshot.volume_ratio_value = float(volume_ratio(df, 20).iloc[-1])

        try:
            snapshot.vwap_value = float(vwap(df).iloc[-1])
        except Exception:
            snapshot.vwap_value = snapshot.ema_20

    def _classify_regime(self, snapshot: MarketSnapshot):
        """Classify current market regime."""
        if snapshot.atr_ratio > 2.0:
            snapshot.regime = "VOLATILE"
        elif snapshot.adx_value > 25:
            snapshot.regime = "TRENDING"
        else:
            snapshot.regime = "RANGING"

    def _calculate_trend(
        self,
        snapshot: MarketSnapshot,
        df: pd.DataFrame,
        df_higher: pd.DataFrame | None,
    ):
        """Determine trend direction and strength."""
        price = snapshot.current_price

        # Primary timeframe EMA alignment
        ema_bullish = price > snapshot.ema_20 > snapshot.ema_50
        ema_bearish = price < snapshot.ema_20 < snapshot.ema_50

        # Higher timeframe confirmation
        htf_bullish = htf_bearish = False
        if df_higher is not None and len(df_higher) >= 50:
            htf_close = df_higher["close"]
            htf_ema20 = float(ema(htf_close, 20).iloc[-1])
            htf_ema50 = float(ema(htf_close, 50).iloc[-1])
            htf_price = float(htf_close.iloc[-1])
            htf_bullish = htf_price > htf_ema20 > htf_ema50
            htf_bearish = htf_price < htf_ema20 < htf_ema50

        if ema_bullish and htf_bullish:
            snapshot.trend = "BULLISH"
            snapshot.trend_strength = min(snapshot.adx_value / 40.0, 1.0)
        elif ema_bearish and htf_bearish:
            snapshot.trend = "BEARISH"
            snapshot.trend_strength = min(snapshot.adx_value / 40.0, 1.0)
        elif ema_bullish or htf_bullish:
            snapshot.trend = "BULLISH"
            snapshot.trend_strength = min(snapshot.adx_value / 60.0, 0.6)
        elif ema_bearish or htf_bearish:
            snapshot.trend = "BEARISH"
            snapshot.trend_strength = min(snapshot.adx_value / 60.0, 0.6)
        else:
            snapshot.trend = "NEUTRAL"
            snapshot.trend_strength = 0.0

    def _calculate_structure(self, snapshot: MarketSnapshot, df: pd.DataFrame):
        """Identify market structure, key levels, OBs, and FVGs."""
        swings = find_swing_points(df, lookback=3)
        snapshot.market_structure = classify_structure(swings)

        support, resistance = find_key_levels(df, swings)
        snapshot.key_support = support
        snapshot.key_resistance = resistance

        obs = find_order_blocks(df, swings)
        snapshot.order_blocks = [
            {
                "direction": ob.direction,
                "top": round(ob.top, 4),
                "bottom": round(ob.bottom, 4),
                "time": ob.time.isoformat(),
            }
            for ob in obs
        ]

        fvgs = find_fair_value_gaps(df)
        snapshot.fair_value_gaps = [
            {
                "direction": fvg.direction,
                "top": round(fvg.top, 4),
                "bottom": round(fvg.bottom, 4),
                "midpoint": round(fvg.midpoint, 4),
                "time": fvg.time.isoformat(),
            }
            for fvg in fvgs
        ]
