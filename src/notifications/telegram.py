"""
Telegram notification service.
Sends formatted signal alerts to a configured Telegram channel/chat.
"""
import asyncio
import httpx
from loguru import logger

from src.config import settings
from src.intelligence.evaluator import SignalResult


class TelegramNotifier:

    def __init__(self):
        self.token = settings.telegram_bot_token
        self.chat_id = settings.telegram_chat_id
        self.base_url = f"https://api.telegram.org/bot{self.token}"

    def is_configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def format_signal(self, signal: SignalResult) -> str:
        direction_icon = "LONG" if signal.direction == "LONG" else "SHORT"
        regime_icon = {"TRENDING": "Trending", "RANGING": "Ranging", "VOLATILE": "Volatile"}.get(
            signal.market_regime, signal.market_regime
        )

        # Confidence bar
        filled = round(signal.confidence * 10)
        conf_bar = "█" * filled + "░" * (10 - filled)

        # Score bar
        score_filled = round(signal.score / 10)
        score_bar = "█" * score_filled + "░" * (10 - score_filled)

        tp_lines = "\n".join(
            f"├ TP{i+1}: `{tp:.4f}`" for i, tp in enumerate(signal.take_profit)
        )

        confluence_lines = "\n".join(f"• {f}" for f in signal.confluence_factors)

        score_parts = []
        bd = signal.score_breakdown
        if bd:
            score_parts = [
                f"Regime: {bd.get('regime_alignment', 0):.0f}/20",
                f"Trend: {bd.get('trend_alignment', 0):.0f}/15",
                f"Structure: {bd.get('structure_quality', 0):.0f}/15",
                f"R/R: {bd.get('rr_quality', 0):.0f}/15",
                f"Volume: {bd.get('volume_confirmation', 0):.0f}/10",
                f"Confluence: {bd.get('confluence_count', 0):.0f}/10",
                f"Level: {bd.get('key_level_quality', 0):.0f}/15",
            ]

        text = f"""*SIGNAL — {signal.asset} {direction_icon}*

*Entry Levels*
├ Entry: `{signal.entry:.4f}`
├ Stop Loss: `{signal.stop_loss:.4f}`
{tp_lines}
├ R/R: `{signal.risk_reward:.1f}:1`
└ Invalidation: `{signal.invalidation_point:.4f}`

*Signal Quality*
├ Score: `{signal.score:.1f}/100` {score_bar}
├ Confidence: `{signal.confidence*100:.0f}%` {conf_bar}
└ Regime: `{regime_icon}` | TF: `{signal.timeframe.upper()}`

*Confluence Factors*
{confluence_lines}

*Reasoning*
_{signal.reasoning[:600]}{"..." if len(signal.reasoning) > 600 else ""}_

_Generated: {signal.created_at.strftime('%Y-%m-%d %H:%M UTC')}_"""

        if score_parts:
            text += f"\n\n*Score Breakdown*\n" + " | ".join(score_parts)

        return text

    async def send_signal(self, signal: SignalResult):
        """Send a signal alert to Telegram."""
        if not self.is_configured():
            logger.warning("Telegram not configured — skipping notification")
            return

        text = self.format_signal(signal)

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/sendMessage",
                    json={
                        "chat_id": self.chat_id,
                        "text": text,
                        "parse_mode": "Markdown",
                        "disable_web_page_preview": True,
                    },
                    timeout=10.0,
                )
                resp.raise_for_status()
                logger.success(f"Telegram: Signal sent for {signal.asset}")
            except Exception as e:
                logger.error(f"Telegram send error: {e}")

    async def send_message(self, text: str):
        """Send a plain text message to Telegram."""
        if not self.is_configured():
            return
        async with httpx.AsyncClient() as client:
            try:
                await client.post(
                    f"{self.base_url}/sendMessage",
                    json={"chat_id": self.chat_id, "text": text, "parse_mode": "Markdown"},
                    timeout=10.0,
                )
            except Exception as e:
                logger.error(f"Telegram message error: {e}")

    def send_signal_sync(self, signal: SignalResult):
        """Synchronous wrapper for use in callbacks."""
        asyncio.create_task(self.send_signal(signal))
