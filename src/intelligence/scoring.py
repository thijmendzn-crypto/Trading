"""
Signal scoring engine. Produces a 0–100 score for each potential setup.
No single factor dominates — prevents gaming or over-weighting.
"""
from dataclasses import dataclass

from src.analysis.market_analyzer import MarketSnapshot


@dataclass
class ScoreBreakdown:
    regime_alignment: float = 0.0
    trend_alignment: float = 0.0
    structure_quality: float = 0.0
    rr_quality: float = 0.0
    volume_confirmation: float = 0.0
    confluence_count: float = 0.0
    key_level_quality: float = 0.0
    total: float = 0.0

    def as_dict(self) -> dict:
        return {k: round(v, 1) for k, v in self.__dict__.items()}


WEIGHTS = {
    "regime_alignment": 20,
    "trend_alignment": 15,
    "structure_quality": 15,
    "rr_quality": 15,
    "volume_confirmation": 10,
    "confluence_count": 10,
    "key_level_quality": 15,
}


def score_signal(
    snapshot: MarketSnapshot,
    direction: str,
    entry: float,
    stop_loss: float,
    take_profits: list[float],
    confluence_factors: list[str],
) -> tuple[float, ScoreBreakdown]:
    """
    Score a signal setup. Returns (total_score, breakdown).
    """
    bd = ScoreBreakdown()

    # 1. Regime alignment (20 pts)
    if snapshot.regime == "TRENDING":
        bd.regime_alignment = WEIGHTS["regime_alignment"]
    elif snapshot.regime == "RANGING":
        # Only partial credit if trading a range boundary
        bd.regime_alignment = WEIGHTS["regime_alignment"] * 0.5
    else:  # VOLATILE
        bd.regime_alignment = 0.0

    # 2. Trend alignment (15 pts)
    trend_matches = (
        (snapshot.trend == "BULLISH" and direction == "LONG") or
        (snapshot.trend == "BEARISH" and direction == "SHORT")
    )
    if trend_matches:
        bd.trend_alignment = WEIGHTS["trend_alignment"] * max(snapshot.trend_strength, 0.3)
    elif snapshot.trend == "NEUTRAL":
        bd.trend_alignment = WEIGHTS["trend_alignment"] * 0.3
    else:
        bd.trend_alignment = 0.0  # Counter-trend — no points

    # 3. Structure quality (15 pts)
    structure_matches = (
        (snapshot.market_structure == "HH_HL" and direction == "LONG") or
        (snapshot.market_structure == "LH_LL" and direction == "SHORT")
    )
    if structure_matches:
        bd.structure_quality = WEIGHTS["structure_quality"]
    elif snapshot.market_structure == "NEUTRAL":
        bd.structure_quality = WEIGHTS["structure_quality"] * 0.3
    else:
        bd.structure_quality = 0.0

    # 4. R/R quality (15 pts) — 4:1 = full points, 2.5:1 = 60%
    if take_profits and entry != stop_loss:
        risk = abs(entry - stop_loss)
        reward = abs(take_profits[-1] - entry)
        rr = reward / risk if risk > 0 else 0
        rr_score = min(rr / 4.0, 1.0)
        bd.rr_quality = WEIGHTS["rr_quality"] * rr_score
    else:
        bd.rr_quality = 0.0

    # 5. Volume confirmation (10 pts)
    vol = snapshot.volume_ratio_value
    if vol >= 1.5:
        bd.volume_confirmation = WEIGHTS["volume_confirmation"]
    elif vol >= 1.0:
        bd.volume_confirmation = WEIGHTS["volume_confirmation"] * 0.6
    elif vol >= 0.7:
        bd.volume_confirmation = WEIGHTS["volume_confirmation"] * 0.3
    else:
        bd.volume_confirmation = 0.0

    # 6. Confluence count (10 pts) — 5+ = full points
    conf_score = min(len(confluence_factors) / 5.0, 1.0)
    bd.confluence_count = WEIGHTS["confluence_count"] * conf_score

    # 7. Key level quality (15 pts) — how close is entry to a structural level
    all_levels = snapshot.key_support + snapshot.key_resistance
    if all_levels and entry > 0:
        nearest = min(all_levels, key=lambda l: abs(l - entry))
        distance_pct = abs(nearest - entry) / entry
        if distance_pct < 0.003:
            bd.key_level_quality = WEIGHTS["key_level_quality"]
        elif distance_pct < 0.007:
            bd.key_level_quality = WEIGHTS["key_level_quality"] * 0.6
        elif distance_pct < 0.015:
            bd.key_level_quality = WEIGHTS["key_level_quality"] * 0.3
        else:
            bd.key_level_quality = 0.0
    else:
        bd.key_level_quality = 0.0

    bd.total = sum([
        bd.regime_alignment,
        bd.trend_alignment,
        bd.structure_quality,
        bd.rr_quality,
        bd.volume_confirmation,
        bd.confluence_count,
        bd.key_level_quality,
    ])

    return round(bd.total, 1), bd
