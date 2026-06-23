"""
AI-powered trade journal.
Records trades, analyzes performance, identifies patterns, and improves over time.
"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import anthropic
from loguru import logger

from src.config import settings


class TradeRecord:
    def __init__(
        self,
        trade_id: str,
        asset: str,
        direction: str,
        setup_type: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        signal_score: float,
        signal_confidence: float,
        market_regime: str,
        timeframe: str,
        confluence_factors: list[str],
        notes: str = "",
    ):
        self.trade_id = trade_id
        self.asset = asset
        self.direction = direction
        self.setup_type = setup_type
        self.entry_price = entry_price
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.signal_score = signal_score
        self.signal_confidence = signal_confidence
        self.market_regime = market_regime
        self.timeframe = timeframe
        self.confluence_factors = confluence_factors
        self.notes = notes
        self.entry_time = datetime.now(timezone.utc)

        # Set after close
        self.exit_price: Optional[float] = None
        self.exit_time: Optional[datetime] = None
        self.outcome: Optional[str] = None  # WIN / LOSS / BE
        self.pnl_pct: Optional[float] = None
        self.r_multiple: Optional[float] = None
        self.mistakes: list[str] = []
        self.ai_feedback: Optional[str] = None

    def close(self, exit_price: float, exit_time: Optional[datetime] = None):
        self.exit_price = exit_price
        self.exit_time = exit_time or datetime.now(timezone.utc)

        risk = abs(self.entry_price - self.stop_loss)
        result = exit_price - self.entry_price if self.direction == "LONG" else self.entry_price - exit_price

        self.r_multiple = round(result / risk, 2) if risk > 0 else 0
        self.pnl_pct = round((result / self.entry_price) * 100, 3)

        if self.r_multiple > 0.1:
            self.outcome = "WIN"
        elif self.r_multiple < -0.1:
            self.outcome = "LOSS"
        else:
            self.outcome = "BE"

    def to_dict(self) -> dict:
        return {
            "trade_id": self.trade_id,
            "asset": self.asset,
            "direction": self.direction,
            "setup_type": self.setup_type,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "signal_score": self.signal_score,
            "signal_confidence": self.signal_confidence,
            "market_regime": self.market_regime,
            "timeframe": self.timeframe,
            "confluence_factors": self.confluence_factors,
            "notes": self.notes,
            "entry_time": self.entry_time.isoformat(),
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "outcome": self.outcome,
            "pnl_pct": self.pnl_pct,
            "r_multiple": self.r_multiple,
            "mistakes": self.mistakes,
            "ai_feedback": self.ai_feedback,
        }


class TradeJournal:
    """
    Persistent trade journal backed by JSON file (MVP).
    Upgrade path: PostgreSQL with analytics queries.
    """

    def __init__(self, data_dir: str = "./data"):
        self.data_path = Path(data_dir) / "journal.json"
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._trades: list[dict] = self._load()

    def _load(self) -> list[dict]:
        if self.data_path.exists():
            try:
                return json.loads(self.data_path.read_text())
            except Exception:
                return []
        return []

    def _save(self):
        self.data_path.write_text(json.dumps(self._trades, indent=2))

    def record_entry(self, trade: TradeRecord) -> str:
        """Record a new trade entry. Returns trade_id."""
        self._trades.append(trade.to_dict())
        self._save()
        logger.info(f"Journal: Recorded entry for {trade.asset} {trade.direction} [{trade.trade_id}]")
        return trade.trade_id

    def record_exit(self, trade_id: str, exit_price: float) -> Optional[dict]:
        """Close a trade by ID and run AI analysis."""
        for trade in self._trades:
            if trade["trade_id"] == trade_id and trade["exit_price"] is None:
                # Calculate result
                risk = abs(trade["entry_price"] - trade["stop_loss"])
                result = (
                    exit_price - trade["entry_price"]
                    if trade["direction"] == "LONG"
                    else trade["entry_price"] - exit_price
                )
                r_multiple = round(result / risk, 2) if risk > 0 else 0

                trade["exit_price"] = exit_price
                trade["exit_time"] = datetime.now(timezone.utc).isoformat()
                trade["pnl_pct"] = round((result / trade["entry_price"]) * 100, 3)
                trade["r_multiple"] = r_multiple
                trade["outcome"] = "WIN" if r_multiple > 0.1 else ("LOSS" if r_multiple < -0.1 else "BE")

                # Run AI feedback
                trade["ai_feedback"] = self._ai_analyze_trade(trade)
                self._save()
                logger.info(f"Journal: Closed {trade['asset']} — {trade['outcome']} ({r_multiple:.2f}R)")
                return trade
        logger.warning(f"Journal: Trade {trade_id} not found or already closed")
        return None

    def _ai_analyze_trade(self, trade: dict) -> str:
        """Get AI coaching feedback on a completed trade."""
        recent_trades = self._trades[-20:]

        prompt = f"""You are an experienced trading coach. Analyze this completed trade and provide specific, actionable feedback.

## COMPLETED TRADE
{json.dumps(trade, indent=2)}

## RECENT TRADE HISTORY (last 20 trades for pattern context)
Win rate: {self._win_rate():.1%}
{json.dumps([{k: v for k, v in t.items() if k in ['asset','direction','outcome','r_multiple','setup_type','market_regime','mistakes']} for t in recent_trades], indent=2)}

## ANALYZE:
1. Was this trade executed according to the system rules?
2. What were the key factors that determined the outcome?
3. If this was a loss: was the setup actually valid? Was it an execution error or just a losing trade in a valid system?
4. If this was a win: what specifically worked well?
5. Any recurring patterns from the recent history that apply?
6. One specific improvement for next time.

Be direct and concise. Max 200 words."""

        try:
            msg = self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
            )
            return msg.content[0].text
        except Exception as e:
            logger.error(f"Journal AI analysis error: {e}")
            return "AI analysis unavailable"

    def get_statistics(self) -> dict:
        """Calculate comprehensive performance statistics."""
        closed = [t for t in self._trades if t.get("outcome")]
        if not closed:
            return {"total_trades": 0}

        wins = [t for t in closed if t["outcome"] == "WIN"]
        losses = [t for t in closed if t["outcome"] == "LOSS"]
        r_multiples = [t["r_multiple"] for t in closed if t.get("r_multiple") is not None]

        win_rate = len(wins) / len(closed) if closed else 0
        avg_win = sum(t["r_multiple"] for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t["r_multiple"] for t in losses) / len(losses) if losses else 0
        expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)

        gross_profit = sum(t["r_multiple"] for t in wins if t["r_multiple"])
        gross_loss = abs(sum(t["r_multiple"] for t in losses if t["r_multiple"]))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        # Drawdown
        equity = 0.0
        peak = 0.0
        max_dd = 0.0
        for r in r_multiples:
            equity += r
            peak = max(peak, equity)
            dd = (peak - equity) / max(peak, 0.01)
            max_dd = max(max_dd, dd)

        # Edge by setup type
        setup_stats = {}
        for trade in closed:
            st = trade.get("setup_type", "unknown")
            if st not in setup_stats:
                setup_stats[st] = {"trades": [], "wins": 0}
            setup_stats[st]["trades"].append(trade)
            if trade["outcome"] == "WIN":
                setup_stats[st]["wins"] += 1

        edge_by_setup = {}
        for st, data in setup_stats.items():
            if len(data["trades"]) >= 5:
                wr = data["wins"] / len(data["trades"])
                avg_r = sum(t["r_multiple"] for t in data["trades"] if t.get("r_multiple")) / len(data["trades"])
                edge_by_setup[st] = {
                    "sample_size": len(data["trades"]),
                    "win_rate": round(wr, 3),
                    "avg_r": round(avg_r, 2),
                }

        return {
            "total_trades": len(closed),
            "win_rate": round(win_rate, 3),
            "avg_win_r": round(avg_win, 2),
            "avg_loss_r": round(avg_loss, 2),
            "expectancy": round(expectancy, 3),
            "profit_factor": round(profit_factor, 2),
            "max_drawdown": round(max_dd, 3),
            "total_r": round(sum(r_multiples), 2),
            "edge_by_setup": edge_by_setup,
        }

    def _win_rate(self) -> float:
        closed = [t for t in self._trades if t.get("outcome")]
        if not closed:
            return 0.0
        wins = sum(1 for t in closed if t["outcome"] == "WIN")
        return wins / len(closed)

    def get_all_trades(self) -> list[dict]:
        return list(self._trades)
