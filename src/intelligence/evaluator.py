"""
AI signal evaluator. Sends market snapshots to Claude API for evaluation.
The AI must reference the knowledge base before generating any signal.
"""
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import anthropic
from loguru import logger

from src.analysis.market_analyzer import MarketSnapshot
from src.config import settings
from .knowledge_engine import KnowledgeEngine
from .scoring import score_signal, ScoreBreakdown


@dataclass
class SignalResult:
    # Core signal fields
    asset: str
    direction: str
    entry: float
    stop_loss: float
    take_profit: list[float]
    risk_reward: float
    confidence: float
    market_regime: str
    timeframe: str
    confluence_factors: list[str]
    invalidation_point: float
    reasoning: str

    # Scoring
    score: float = 0.0
    score_breakdown: dict = field(default_factory=dict)

    # Status
    approved: bool = False
    rejection_reason: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "asset": self.asset,
            "direction": self.direction,
            "entry": self.entry,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "risk_reward": round(self.risk_reward, 2),
            "confidence": round(self.confidence, 2),
            "market_regime": self.market_regime,
            "timeframe": self.timeframe,
            "confluence_factors": self.confluence_factors,
            "invalidation_point": self.invalidation_point,
            "reasoning": self.reasoning,
            "score": self.score,
            "score_breakdown": self.score_breakdown,
            "approved": self.approved,
            "rejection_reason": self.rejection_reason,
            "created_at": self.created_at.isoformat(),
        }


class SignalEvaluator:
    """
    Evaluates market snapshots and generates trading signals.
    Every signal must pass the knowledge base, regime gates, and scoring threshold.
    """

    def __init__(self, knowledge_dir: str = "./knowledge"):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.knowledge = KnowledgeEngine(knowledge_dir)

    def evaluate(self, snapshot: MarketSnapshot) -> Optional[SignalResult]:
        """
        Full evaluation pipeline. Returns None if no quality setup found.
        Rejection reasons are logged for later analysis.
        """
        # Gate 1: Regime filter
        if snapshot.regime == "VOLATILE":
            logger.info(f"{snapshot.symbol}: Rejected — VOLATILE regime")
            return None

        # Gate 2: Volume filter
        if snapshot.volume_ratio_value < 0.7:
            logger.info(f"{snapshot.symbol}: Rejected — Low volume ({snapshot.volume_ratio_value:.2f}x)")
            return None

        # Get targeted knowledge context
        query = (
            f"{snapshot.symbol} {snapshot.trend} {snapshot.regime} "
            f"{snapshot.market_structure} entry exit risk"
        )
        kb_context = self.knowledge.get_relevant_context(query, max_chunks=10)

        # AI evaluation
        signal = self._ai_evaluate(snapshot, kb_context)
        if signal is None:
            return None

        # Score the signal
        score, breakdown = score_signal(
            snapshot=snapshot,
            direction=signal.direction,
            entry=signal.entry,
            stop_loss=signal.stop_loss,
            take_profits=signal.take_profit,
            confluence_factors=signal.confluence_factors,
        )
        signal.score = score
        signal.score_breakdown = breakdown.as_dict()

        # Gate 3: Score threshold
        if score < settings.min_signal_score:
            signal.approved = False
            signal.rejection_reason = f"Score {score:.1f} below minimum {settings.min_signal_score}"
            logger.info(f"{snapshot.symbol}: Rejected — {signal.rejection_reason}")
            return signal  # Return for logging even if rejected

        # Gate 4: R/R threshold
        if signal.risk_reward < settings.min_rr:
            signal.approved = False
            signal.rejection_reason = f"R/R {signal.risk_reward:.2f} below minimum {settings.min_rr}"
            logger.info(f"{snapshot.symbol}: Rejected — {signal.rejection_reason}")
            return signal

        # Gate 5: Confidence threshold
        if signal.confidence < settings.min_confidence:
            signal.approved = False
            signal.rejection_reason = f"Confidence {signal.confidence:.2f} below minimum {settings.min_confidence}"
            logger.info(f"{snapshot.symbol}: Rejected — {signal.rejection_reason}")
            return signal

        # Gate 6: Minimum confluence
        if len(signal.confluence_factors) < 3:
            signal.approved = False
            signal.rejection_reason = "Insufficient confluence factors (minimum 3 required)"
            logger.info(f"{snapshot.symbol}: Rejected — {signal.rejection_reason}")
            return signal

        signal.approved = True
        logger.success(
            f"SIGNAL APPROVED: {snapshot.symbol} {signal.direction} | "
            f"Score={score:.1f} | Confidence={signal.confidence:.0%} | R/R={signal.risk_reward:.1f}"
        )
        return signal

    def _ai_evaluate(self, snapshot: MarketSnapshot, kb_context: str) -> Optional[SignalResult]:
        """Call Claude to evaluate the market snapshot."""
        snapshot_dict = snapshot.to_dict()

        prompt = f"""You are an institutional-grade trading analyst. Your role is to evaluate market conditions and identify only the highest-probability setups.

## KNOWLEDGE BASE (Your Trading Rules — Follow These Exactly)
{kb_context}

## CURRENT MARKET SNAPSHOT
{json.dumps(snapshot_dict, indent=2)}

## EVALUATION INSTRUCTIONS

1. First, review the market regime against the knowledge base regime rules.
2. Check if the current market structure supports a trade in either direction.
3. Identify if any of the valid setup types (from the strategy framework) exist right now.
4. If no qualifying setup exists, respond with verdict: "NO_SETUP" and a brief reason.
5. If a setup exists, calculate precise entry, stop, and target levels based on the key levels shown.
6. Confidence must reflect genuine edge probability. Be conservative. 0.65 is a good trade. 0.85 is exceptional. Never inflate.
7. List only real confluence factors present in the data — do not invent them.
8. The reasoning must be specific: reference which setup type, which rule from the knowledge base, and which exact price levels justify the trade.

## CRITICAL RULES
- Never generate a signal just because there is price movement
- Never take a counter-trend trade unless a liquidity sweep + reversal setup is confirmed
- Stop loss must be at a logical structural level, not arbitrary distance
- If fewer than 3 genuine confluence factors exist, verdict must be NO_SETUP

## REQUIRED OUTPUT (JSON only, no extra text)
{{
  "verdict": "SETUP_FOUND" | "NO_SETUP",
  "rejection_reason": "string explaining why no setup (only if NO_SETUP)",
  "direction": "LONG" | "SHORT",
  "entry": <float>,
  "stop_loss": <float>,
  "take_profit": [<float_tp1>, <float_tp2>],
  "risk_reward": <float>,
  "confidence": <float between 0.0 and 1.0>,
  "confluence_factors": ["factor1", "factor2", ...],
  "invalidation_point": <float>,
  "reasoning": "Detailed explanation referencing specific knowledge base rules and price levels"
}}"""

        try:
            message = self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}],
            )

            content = message.content[0].text.strip()

            # Extract JSON block
            start = content.find("{")
            end = content.rfind("}") + 1
            if start == -1 or end == 0:
                logger.error(f"No JSON found in AI response: {content[:200]}")
                return None

            data = json.loads(content[start:end])

            if data.get("verdict") == "NO_SETUP":
                logger.info(f"{snapshot.symbol}: AI rejected — {data.get('rejection_reason', 'No reason given')}")
                return None

            # Validate required fields
            required = ["direction", "entry", "stop_loss", "take_profit", "confidence", "confluence_factors", "reasoning"]
            if not all(k in data for k in required):
                logger.error(f"Missing required fields in AI response: {data.keys()}")
                return None

            entry = float(data["entry"])
            stop_loss = float(data["stop_loss"])
            take_profits = [float(t) for t in data["take_profit"]]

            # Calculate actual R/R
            risk = abs(entry - stop_loss)
            reward = abs(take_profits[-1] - entry) if take_profits else 0
            rr = round(reward / risk, 2) if risk > 0 else 0

            return SignalResult(
                asset=snapshot.symbol,
                direction=data["direction"],
                entry=entry,
                stop_loss=stop_loss,
                take_profit=take_profits,
                risk_reward=rr,
                confidence=float(data["confidence"]),
                market_regime=snapshot.regime,
                timeframe=snapshot.timeframe,
                confluence_factors=data["confluence_factors"],
                invalidation_point=float(data.get("invalidation_point", stop_loss)),
                reasoning=data["reasoning"],
            )

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error in AI response: {e}")
            return None
        except Exception as e:
            logger.error(f"AI evaluation error for {snapshot.symbol}: {e}")
            return None
