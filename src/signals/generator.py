"""
Signal generation orchestrator.
Fetches data, runs analysis, evaluates with AI, and dispatches approved signals.
"""
import asyncio
from datetime import datetime, timezone
from typing import Callable, Optional

from loguru import logger

from src.config import settings
from src.data.providers.binance import BinanceProvider
from src.analysis.market_analyzer import MarketAnalyzer
from src.intelligence.evaluator import SignalEvaluator, SignalResult


class SignalGenerator:
    """
    Main orchestrator: runs the full pipeline from data → signal.
    Call run_scan() to evaluate all configured symbols once.
    Call run_loop() to run continuously on a schedule.
    """

    def __init__(
        self,
        knowledge_dir: str = "./knowledge",
        on_signal: Optional[Callable[[SignalResult], None]] = None,
    ):
        self.provider = BinanceProvider()
        self.analyzer = MarketAnalyzer()
        self.evaluator = SignalEvaluator(knowledge_dir=knowledge_dir)
        self.on_signal = on_signal
        self.signal_history: list[SignalResult] = []

    async def run_scan(self) -> list[SignalResult]:
        """
        Scan all configured symbols once. Returns approved signals.
        """
        symbols = settings.symbol_list
        logger.info(f"Starting scan for {symbols}")

        approved = []
        for symbol in symbols:
            try:
                signal = await self._evaluate_symbol(symbol)
                if signal:
                    self.signal_history.append(signal)
                    if signal.approved:
                        approved.append(signal)
                        if self.on_signal:
                            self.on_signal(signal)
            except Exception as e:
                logger.error(f"Error evaluating {symbol}: {e}")

        logger.info(f"Scan complete — {len(approved)} approved signals from {len(symbols)} symbols")
        return approved

    async def run_loop(self, interval_minutes: int = 60):
        """
        Run continuous scanning. Evaluates every interval_minutes on 1H candle close.
        """
        logger.info(f"Starting signal loop — scanning every {interval_minutes} minutes")
        while True:
            try:
                await self.run_scan()
            except Exception as e:
                logger.error(f"Scan loop error: {e}")
            await asyncio.sleep(interval_minutes * 60)

    async def _evaluate_symbol(self, symbol: str) -> Optional[SignalResult]:
        """Run the full pipeline for a single symbol."""
        logger.debug(f"Evaluating {symbol}...")

        # Fetch data for primary (1H) and higher (4H) timeframes
        data = await self.provider.fetch_multi_timeframe(
            symbol=symbol,
            timeframes=["1h", "4h"],
        )

        df_1h = data["1h"]
        df_4h = data["4h"]

        if df_1h.empty or len(df_1h) < 50:
            logger.warning(f"{symbol}: Insufficient data")
            return None

        # Market analysis
        snapshot = self.analyzer.analyze(
            symbol=symbol,
            df_primary=df_1h,
            df_higher=df_4h,
        )
        snapshot.timeframe = "1h"

        # AI evaluation
        return self.evaluator.evaluate(snapshot)
