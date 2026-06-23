"""
Backtesting engine with walk-forward validation and Monte Carlo simulation.
Designed to minimize overfitting and give honest performance estimates.
"""
import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

import numpy as np
import pandas as pd
from loguru import logger

from src.analysis.market_analyzer import MarketAnalyzer, MarketSnapshot
from src.intelligence.scoring import score_signal


@dataclass
class BacktestTrade:
    symbol: str
    direction: str
    entry: float
    stop_loss: float
    take_profit: list[float]
    entry_time: datetime
    exit_time: datetime | None = None
    exit_price: float | None = None
    r_multiple: float = 0.0
    outcome: str = ""  # WIN / LOSS / BE


@dataclass
class BacktestResults:
    period_start: str
    period_end: str
    total_trades: int
    win_rate: float
    avg_r: float
    expectancy: float
    profit_factor: float
    sharpe_ratio: float
    max_drawdown: float
    max_drawdown_duration_bars: int
    total_r: float
    equity_curve: list[float]
    trades: list[BacktestTrade]

    # Walk-forward
    is_sharpe: float = 0.0
    oos_sharpe: float = 0.0
    overfitting_score: float = 0.0  # OOS/IS — higher is better, >0.7 acceptable

    # Monte Carlo
    mc_95_drawdown: float = 0.0   # 95th percentile worst drawdown
    mc_5_return: float = 0.0      # 5th percentile best return (pessimistic)

    def summary(self) -> str:
        return (
            f"Trades={self.total_trades} | WR={self.win_rate:.1%} | "
            f"Expectancy={self.expectancy:.2f}R | PF={self.profit_factor:.2f} | "
            f"Sharpe={self.sharpe_ratio:.2f} | MaxDD={self.max_drawdown:.1%} | "
            f"Overfitting={self.overfitting_score:.2f}"
        )


class BacktestEngine:
    """
    Event-driven backtesting engine.
    Simulates signal evaluation bar-by-bar on historical data.
    """

    def __init__(
        self,
        min_score: float = 70.0,
        min_rr: float = 2.5,
        commission_pct: float = 0.001,  # 0.1% per side
        slippage_pct: float = 0.0005,   # 0.05% slippage
    ):
        self.min_score = min_score
        self.min_rr = min_rr
        self.commission = commission_pct
        self.slippage = slippage_pct
        self.analyzer = MarketAnalyzer()

    def run(
        self,
        df: pd.DataFrame,
        symbol: str,
        signal_func: Callable[[MarketSnapshot], tuple | None],
        warmup_bars: int = 200,
    ) -> BacktestResults:
        """
        Run a full backtest.

        Args:
            df: OHLCV DataFrame (entire history)
            symbol: Trading pair
            signal_func: Function that takes a MarketSnapshot and returns
                         (direction, entry, stop, [tp1, tp2]) or None
            warmup_bars: Bars to skip at start for indicator warmup
        """
        trades: list[BacktestTrade] = []
        active_trade: BacktestTrade | None = None

        logger.info(f"Backtesting {symbol} on {len(df)} bars...")

        for i in range(warmup_bars, len(df)):
            current_bar = df.iloc[i]
            window = df.iloc[:i + 1]

            # Check if active trade hit TP or SL
            if active_trade:
                active_trade = self._update_trade(active_trade, current_bar)
                if active_trade.exit_price is not None:
                    trades.append(active_trade)
                    active_trade = None
                continue  # One trade at a time

            # Analyze current state
            try:
                snapshot = self.analyzer.analyze(symbol=symbol, df_primary=window)
                snapshot.timeframe = "1h"
            except Exception:
                continue

            # Run signal function
            result = signal_func(snapshot)
            if result is None:
                continue

            direction, entry, stop, tps = result

            # Validate
            risk = abs(entry - stop)
            reward = abs(tps[-1] - entry) if tps else 0
            rr = reward / risk if risk > 0 else 0

            if rr < self.min_rr:
                continue

            # Score signal
            score, _ = score_signal(
                snapshot=snapshot,
                direction=direction,
                entry=entry,
                stop_loss=stop,
                take_profits=tps,
                confluence_factors=["placeholder"],  # Real signals would have actual factors
            )

            if score < self.min_score:
                continue

            # Apply slippage to entry
            slip = entry * self.slippage
            actual_entry = entry + slip if direction == "LONG" else entry - slip

            active_trade = BacktestTrade(
                symbol=symbol,
                direction=direction,
                entry=actual_entry,
                stop_loss=stop,
                take_profit=tps,
                entry_time=current_bar.name if hasattr(current_bar, 'name') else datetime.now(),
            )

        # Close any open trade at end
        if active_trade:
            last_close = float(df["close"].iloc[-1])
            active_trade.exit_price = last_close
            active_trade.exit_time = df.index[-1]
            risk = abs(active_trade.entry - active_trade.stop_loss)
            result_pnl = (last_close - active_trade.entry if active_trade.direction == "LONG"
                          else active_trade.entry - last_close)
            active_trade.r_multiple = round(result_pnl / risk, 2) if risk > 0 else 0
            active_trade.outcome = "WIN" if active_trade.r_multiple > 0 else "LOSS"
            trades.append(active_trade)

        return self._calculate_results(trades, df)

    def _update_trade(self, trade: BacktestTrade, bar: pd.Series) -> BacktestTrade:
        """Check if the current bar hits stop or take profit."""
        high = float(bar["high"])
        low = float(bar["low"])

        # Commission cost
        comm = trade.entry * self.commission * 2  # Entry + exit

        if trade.direction == "LONG":
            if low <= trade.stop_loss:
                trade.exit_price = trade.stop_loss
                trade.exit_time = bar.name
                risk = abs(trade.entry - trade.stop_loss)
                trade.r_multiple = round(-1.0 - (comm / trade.entry / risk * 100), 2)
                trade.outcome = "LOSS"
            elif trade.take_profit and high >= trade.take_profit[-1]:
                trade.exit_price = trade.take_profit[-1]
                trade.exit_time = bar.name
                risk = abs(trade.entry - trade.stop_loss)
                reward = abs(trade.take_profit[-1] - trade.entry)
                trade.r_multiple = round(reward / risk - (comm / trade.entry), 2)
                trade.outcome = "WIN"
        else:  # SHORT
            if high >= trade.stop_loss:
                trade.exit_price = trade.stop_loss
                trade.exit_time = bar.name
                risk = abs(trade.entry - trade.stop_loss)
                trade.r_multiple = round(-1.0 - (comm / trade.entry / risk * 100), 2)
                trade.outcome = "LOSS"
            elif trade.take_profit and low <= trade.take_profit[-1]:
                trade.exit_price = trade.take_profit[-1]
                trade.exit_time = bar.name
                risk = abs(trade.entry - trade.stop_loss)
                reward = abs(trade.entry - trade.take_profit[-1])
                trade.r_multiple = round(reward / risk - (comm / trade.entry), 2)
                trade.outcome = "WIN"

        return trade

    def _calculate_results(self, trades: list[BacktestTrade], df: pd.DataFrame) -> BacktestResults:
        if not trades:
            return BacktestResults(
                period_start=str(df.index[0]),
                period_end=str(df.index[-1]),
                total_trades=0,
                win_rate=0, avg_r=0, expectancy=0, profit_factor=0,
                sharpe_ratio=0, max_drawdown=0, max_drawdown_duration_bars=0,
                total_r=0, equity_curve=[], trades=[],
            )

        r_multiples = [t.r_multiple for t in trades]
        wins = [r for r in r_multiples if r > 0]
        losses = [r for r in r_multiples if r <= 0]

        win_rate = len(wins) / len(trades)
        avg_r = np.mean(r_multiples)
        avg_win = np.mean(wins) if wins else 0
        avg_loss = np.mean(losses) if losses else 0
        expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)

        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        # Equity curve and drawdown
        equity = np.cumsum(r_multiples)
        equity_list = equity.tolist()
        peak = np.maximum.accumulate(equity)
        drawdown = (peak - equity) / np.maximum(np.abs(peak), 0.01)
        max_drawdown = float(drawdown.max())

        # Drawdown duration
        in_drawdown = drawdown > 0.01
        max_dd_duration = 0
        current_dd = 0
        for v in in_drawdown:
            current_dd = current_dd + 1 if v else 0
            max_dd_duration = max(max_dd_duration, current_dd)

        # Sharpe ratio (using R as return unit)
        sharpe = float(np.mean(r_multiples) / np.std(r_multiples)) * np.sqrt(252) if len(r_multiples) > 1 else 0

        # Monte Carlo
        mc_95, mc_5 = self._monte_carlo(r_multiples)

        return BacktestResults(
            period_start=str(df.index[0]),
            period_end=str(df.index[-1]),
            total_trades=len(trades),
            win_rate=round(win_rate, 3),
            avg_r=round(avg_r, 3),
            expectancy=round(expectancy, 3),
            profit_factor=round(profit_factor, 2),
            sharpe_ratio=round(sharpe, 2),
            max_drawdown=round(max_drawdown, 3),
            max_drawdown_duration_bars=max_dd_duration,
            total_r=round(float(equity[-1]), 2),
            equity_curve=equity_list,
            trades=trades,
            mc_95_drawdown=mc_95,
            mc_5_return=mc_5,
        )

    def _monte_carlo(self, r_multiples: list[float], simulations: int = 1000) -> tuple[float, float]:
        """
        Monte Carlo simulation by shuffling trade order.
        Returns (95th_percentile_drawdown, 5th_percentile_final_return).
        """
        if len(r_multiples) < 10:
            return 0.0, 0.0

        drawdowns = []
        final_returns = []

        for _ in range(simulations):
            shuffled = r_multiples.copy()
            random.shuffle(shuffled)
            equity = np.cumsum(shuffled)
            peak = np.maximum.accumulate(equity)
            dd = (peak - equity) / np.maximum(np.abs(peak), 0.01)
            drawdowns.append(float(dd.max()))
            final_returns.append(float(equity[-1]))

        mc_95 = round(float(np.percentile(drawdowns, 95)), 3)
        mc_5 = round(float(np.percentile(final_returns, 5)), 2)

        return mc_95, mc_5

    def walk_forward(
        self,
        df: pd.DataFrame,
        symbol: str,
        signal_func: Callable,
        is_pct: float = 0.6,
        oos_pct: float = 0.2,
        n_windows: int = 5,
    ) -> list[BacktestResults]:
        """
        Walk-forward testing: train on IS, validate on OOS, slide forward.
        The overfitting_score (OOS/IS Sharpe) tells you if the edge is real.
        """
        total = len(df)
        is_size = int(total * is_pct)
        oos_size = int(total * oos_pct)
        step = (total - is_size - oos_size) // max(n_windows - 1, 1)

        results = []
        for i in range(n_windows):
            start = i * step
            is_end = start + is_size
            oos_end = is_end + oos_size

            if oos_end > total:
                break

            is_df = df.iloc[start:is_end]
            oos_df = df.iloc[is_end:oos_end]

            is_result = self.run(is_df, symbol, signal_func)
            oos_result = self.run(oos_df, symbol, signal_func)

            if is_result.sharpe_ratio != 0:
                oos_result.is_sharpe = is_result.sharpe_ratio
                oos_result.oos_sharpe = oos_result.sharpe_ratio
                oos_result.overfitting_score = round(
                    oos_result.sharpe_ratio / abs(is_result.sharpe_ratio), 2
                )

            results.append(oos_result)
            logger.info(
                f"WF Window {i+1}: IS={is_result.summary()} | "
                f"OOS={oos_result.summary()} | Overfitting={oos_result.overfitting_score:.2f}"
            )

        return results
