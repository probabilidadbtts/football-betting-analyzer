"""
Cálculo de value, EV, Kelly y clasificación de oportunidades.
"""
from __future__ import annotations

from ..config import (
    MIN_EDGE, MIN_EV_PERCENT, KELLY_FRACTION, BANKROLL_UNITS,
    MAX_STAKE_UNITS, LEVEL1_EDGE, LEVEL1_CONTEXT, LEVEL2_EDGE, LEVEL2_CONTEXT,
)


def implied_prob(odds: float) -> float:
    return 1.0 / odds if odds and odds > 1.0 else 0.0


def edge(p_model: float, odds: float) -> float:
    """p_model - p_implied."""
    return p_model - implied_prob(odds)


def expected_value_pct(p_model: float, odds: float) -> float:
    """(p * odds - 1) * 100."""
    if not odds or odds <= 1.0:
        return 0.0
    return (p_model * odds - 1.0) * 100.0


def kelly_fraction(p_model: float, odds: float) -> float:
    """f* = (p*b - q) / b  donde b = odds-1, q = 1-p."""
    if not odds or odds <= 1.0 or p_model <= 0:
        return 0.0
    b = odds - 1.0
    f = (p_model * odds - 1.0) / b
    return max(0.0, f)


def kelly_stake(p_model: float, odds: float) -> float:
    f = kelly_fraction(p_model, odds)
    stake = f * KELLY_FRACTION * BANKROLL_UNITS
    return min(stake, MAX_STAKE_UNITS)


def has_value(p_model: float, odds: float) -> bool:
    e = edge(p_model, odds)
    ev = expected_value_pct(p_model, odds)
    return e >= MIN_EDGE and ev >= MIN_EV_PERCENT


def classify_opportunity(
    p_model: float,
    odds: float,
    context_score: float,
) -> int:
    """
    1 = Alta convicción (edge fuerte + contexto sólido)
    2 = Intermedio (edge decente + contexto aceptable)
    3 = Descartable
    """
    e = edge(p_model, odds)
    if e >= LEVEL1_EDGE and context_score >= LEVEL1_CONTEXT and has_value(p_model, odds):
        return 1
    if e >= LEVEL2_EDGE and context_score >= LEVEL2_CONTEXT and has_value(p_model, odds):
        return 2
    return 3


def blend_probs(
    p_poisson: float,
    p_market: float | None,
    form_adj: float = 0.0,
    weight_poisson: float = 0.55,
    weight_market: float = 0.35,
    weight_form: float = 0.10,
) -> float:
    """Ensemble: modelo + mercado + ajuste de forma."""
    if p_market is not None and 0.01 < p_market < 0.99:
        w_p = weight_poisson
        w_m = weight_market
        total_w = w_p + w_m
        base = (w_p / total_w) * p_poisson + (w_m / total_w) * p_market
    else:
        base = p_poisson

    adj = max(-0.06, min(0.06, form_adj))
    final = base + adj * weight_form * 3
    return min(0.97, max(0.03, final))
