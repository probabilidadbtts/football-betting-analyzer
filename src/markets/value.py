"""
Lógica matemática de ensamble bayesiano, cálculo de Edge y Criterio de Kelly fraccional.
Diseñado para entornos de ejecución concurrente de alta disponibilidad y baja latencia.
"""
from __future__ import annotations

import math
from typing import Mapping, Sequence, TypedDict

from ..config import (
    BANKROLL_UNITS,
    KELLY_FRACTION,
    LEVEL1_CONTEXT,
    LEVEL1_EDGE,
    LEVEL2_CONTEXT,
    LEVEL2_EDGE,
    MAX_STAKE_UNITS,
    MIN_EDGE,
    MIN_EV_PERCENT,
    WEIGHT_MARKET,
    WEIGHT_MODEL,
)

__all__ = [
    "BetValueResult",
    "blend_discrete_distribution",
    "calculate_kelly_stake",
    "evaluate_bet_value",
]


class BetValueResult(TypedDict):
    """Estructura canónica de salida para la evaluación de valor y dimensionamiento de posición."""
    edge: float
    ev: float
    has_value: bool
    level: int
    stake: float


def _is_valid_prob(val: float) -> bool:
    """Valida si un flotante pertenece estrictamente al intervalo cerrado [0.0, 1.0]."""
    return isinstance(val, (int, float)) and not math.isnan(val) and 0.0 <= val <= 1.0


def blend_discrete_distribution(
    model_probs: Mapping[str, float],
    market_probs: Mapping[str, float],
    keys: Sequence[str],
) -> dict[str, float]:
    """
    Combina linealmente distribuciones probabilísticas discretas mediante ponderación de credibilidad bayesiana.
    Garantiza axiomáticamente la no negatividad y la suma unitaria (sum(P) = 1.0).

    Args:
        model_probs: Distribución generada por el modelo predictivo (ej. Poisson / xG).
        market_probs: Distribución de consenso o desvigorizada del mercado (Fair Odds).
        keys: Espacio muestral mutuamente excluyente y exhaustivo (ej. ["1", "X", "2"]).

    Returns:
        dict[str, float]: Distribución combinada y normalizada a 4 decimales.
    """
    if not keys:
        return {}

    n_keys = len(keys)
    default_uniform = {k: round(1.0 / n_keys, 4) for k in keys}

    # Verificación de integridad de mercado
    has_full_market = (
        bool(market_probs)
        and all(k in market_probs and _is_valid_prob(market_probs[k]) for k in keys)
    )

    # Normalización dinámica de pesos para resiliencia ante configuraciones descentradas
    total_weight = WEIGHT_MODEL + WEIGHT_MARKET
    w_model = WEIGHT_MODEL / total_weight if total_weight > 0 else 1.0
    w_market = WEIGHT_MARKET / total_weight if total_weight > 0 else 0.0

    blended: dict[str, float] = {}

    for k in keys:
        p_model = model_probs.get(k, 0.0)
        p_model = p_model if _is_valid_prob(p_model) else 0.0

        if has_full_market:
            p_mkt = market_probs[k]
            combined = (w_model * p_model) + (w_market * p_mkt)
        else:
            combined = p_model

        blended[k] = max(0.0, combined)

    total_mass = sum(blended.values())
    if math.isnan(total_mass) or total_mass <= 1e-9:
        return default_uniform

    # Normalización matemática estricta
    normalized = {k: v / total_mass for k, v in blended.items()}
    
    # Redondeo preservando invariante de probabilidad
    rounded = {k: round(v, 4) for k, v in normalized.items()}
    diff = round(1.0 - sum(rounded.values()), 4)
    if diff != 0.0:
        first_key = keys[0]
        rounded[first_key] = round(rounded[first_key] + diff, 4)

    return rounded


def calculate_kelly_stake(prob: float, decimal_odds: float) -> float:
    """
    Calcula el tamaño de posición óptimo aplicando el Criterio de Kelly fraccional.
    f* = (p * b - q) / b = (p * decimal_odds - 1) / (decimal_odds - 1)

    Args:
        prob: Probabilidad real estimada de victoria P(E) ∈ [0.0, 1.0].
        decimal_odds: Cuota decimal cotizada en el mercado (debe ser > 1.0).

    Returns:
        float: Unidades de stake recomendadas acotadas a [0.0, MAX_STAKE_UNITS].
    """
    if (
        not _is_valid_prob(prob)
        or math.isnan(decimal_odds)
        or decimal_odds <= 1.0
        or prob <= 0.0
    ):
        return 0.0

    b = decimal_odds - 1.0
    q = 1.0 - prob
    f_star = (prob * b - q) / b

    if math.isnan(f_star) or f_star <= 0.0:
        return 0.0

    raw_stake = f_star * max(0.0, KELLY_FRACTION) * max(0.0, BANKROLL_UNITS)
    bounded_stake = min(raw_stake, float(MAX_STAKE_UNITS))

    return round(max(0.0, bounded_stake), 2)


def evaluate_bet_value(
    prob_blended: float,
    fair_market_prob: float | None,
    best_odds: float,
    context_score: float,
) -> BetValueResult:
    """
    Evalúa matemáticamente la existencia de Valor Esperado Positivo (+EV) frente a la casa
    y audita la superioridad frente al consenso justo de mercado (Closing Line Value proxy).

    Args:
        prob_blended: Probabilidad combinada calculada para el evento.
        fair_market_prob: Probabilidad justa de mercado desvigorizada (opcional).
        best_odds: Cuota decimal óptima disponible en el agregado de casas.
        context_score: Métrica cualitativa/contextual calculada para el evento.

    Returns:
        BetValueResult: Diccionario tipado con Edge, EV%, Bandera de Valor, Nivel y Stake.
    """
    if (
        not _is_valid_prob(prob_blended)
        or math.isnan(best_odds)
        or best_odds <= 1.0
    ):
        return {
            "edge": 0.0,
            "ev": 0.0,
            "has_value": False,
            "level": 3,
            "stake": 0.0,
        }

    safe_context_score = 0.0 if math.isnan(context_score) else context_score
    implied_prob_bookmaker = 1.0 / best_odds

    edge = prob_blended - implied_prob_bookmaker
    ev_pct = ((prob_blended * best_odds) - 1.0) * 100.0

    # Filtro de robustez frente al mercado desvigorizado (evita overfit ante líneas eficientes)
    beats_fair_market = True
    if fair_market_prob is not None and _is_valid_prob(fair_market_prob):
        beats_fair_market = prob_blended > (fair_market_prob + 0.005)

    has_value = (
        edge >= MIN_EDGE
        and ev_pct >= MIN_EV_PERCENT
        and beats_fair_market
    )

    level = 3
    if has_value:
        if edge >= LEVEL1_EDGE and safe_context_score >= LEVEL1_CONTEXT:
            level = 1
        elif edge >= LEVEL2_EDGE and safe_context_score >= LEVEL2_CONTEXT:
            level = 2

    stake = calculate_kelly_stake(prob_blended, best_odds) if has_value else 0.0

    return {
        "edge": round(edge, 4),
        "ev": round(ev_pct, 2),
        "has_value": has_value,
        "level": level,
        "stake": stake,
    }