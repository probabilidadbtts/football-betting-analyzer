"""
Lógica matemática de ensamble bayesiano, cálculo de Edge y Criterio de Kelly fraccional.
"""
from __future__ import annotations

from ..config import (
    MIN_EDGE, MIN_EV_PERCENT, KELLY_FRACTION,
    BANKROLL_UNITS, MAX_STAKE_UNITS,
    WEIGHT_MODEL, WEIGHT_MARKET,
    LEVEL1_EDGE, LEVEL1_CONTEXT, LEVEL2_EDGE, LEVEL2_CONTEXT,
)


def blend_discrete_distribution(
    model_probs: dict[str, float],
    market_probs: dict[str, float],
    keys: list[str],
) -> dict[str, float]:
    """Combina distribuciones probabilísticas completas asegurando suma unitaria."""
    blended: dict[str, float] = {}
    has_full_market = all(k in market_probs for k in keys)

    for k in keys:
        pm = model_probs.get(k, 0.0)
        if has_full_market:
            p_mkt = market_probs[k]
            blended[k] = (WEIGHT_MODEL * pm) + (WEIGHT_MARKET * p_mkt)
        else:
            blended[k] = pm

    total = sum(blended.values())
    if total > 0:
        return {k: round(v / total, 4) for k, v in blended.items()}
    return {k: round(1.0 / len(keys), 4) for k in keys}


def calculate_kelly_stake(prob: float, decimal_odds: float) -> float:
    """Kelly = (p * b - q) / b con b = cuota - 1."""
    if decimal_odds <= 1.0 or prob <= 0.0:
        return 0.0
    b = decimal_odds - 1.0
    q = 1.0 - prob
    f_star = (prob * b - q) / b
    if f_star <= 0:
        return 0.0

    raw_stake = f_star * KELLY_FRACTION * BANKROLL_UNITS
    return min(round(raw_stake, 2), MAX_STAKE_UNITS)


def evaluate_bet_value(
    prob_blended: float,
    fair_market_prob: float | None,
    best_odds: float,
    context_score: float,
) -> dict:
    """Evalúa si existe valor real positivo frente al mercado y clasifica la oportunidad."""
    implied_prob_bookmaker = 1.0 / best_odds
    edge = prob_blended - implied_prob_bookmaker
    ev_pct = (prob_blended * best_odds - 1.0) * 100.0

    # Valor real: el modelo debe superar la cuota ofrecida Y la probabilidad justa del mercado
    beats_fair_market = (fair_market_prob is None) or (prob_blended > fair_market_prob + 0.005)
    has_value = (edge >= MIN_EDGE) and (ev_pct >= MIN_EV_PERCENT) and beats_fair_market

    level = 3
    if has_value:
        if edge >= LEVEL1_EDGE and context_score >= LEVEL1_CONTEXT:
            level = 1
        elif edge >= LEVEL2_EDGE and context_score >= LEVEL2_CONTEXT:
            level = 2

    stake = calculate_kelly_stake(prob_blended, best_odds) if has_value else 0.0

    return {
        "edge": round(edge, 4),
        "ev": round(ev_pct, 2),
        "has_value": has_value,
        "level": level,
        "stake": stake,
    }
