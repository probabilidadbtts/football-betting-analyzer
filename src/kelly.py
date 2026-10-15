"""
Cálculo de Value Odds y Kelly Criterion.
"""
from .config import KELLY_FRACTION, BANKROLL_UNITS


def implied_probability(odds: float) -> float:
    """Probabilidad implícita = 1/cuota."""
    return 1.0 / odds if odds > 1.0 else 0.0


def has_value(p_model: float, odds: float, margin: float = 0.03) -> bool:
    """
    ¿Hay value? P_modelo > P_implícita + margen.
    """
    p_implied = implied_probability(odds)
    return p_model > p_implied + margin


def ev_percent(p_model: float, odds: float) -> float:
    """Expected Value en %."""
    return (p_model * odds - 1.0) * 100


def kelly_stake(p_model: float, odds: float, fraction: float = KELLY_FRACTION) -> float:
    """
    Kelly Criterion. Devuelve stake en unidades.
    f* = (p*odds - 1) / (odds - 1)
    """
    if odds <= 1.0:
        return 0.0
    b = odds - 1.0
    f = (p_model * odds - 1.0) / b
    f = max(0.0, f)  # No apostar si f < 0
    return f * fraction * BANKROLL_UNITS


def breakeven_odds(p_model: float) -> float:
    """Cuota mínima para breakeven."""
    return 1.0 / p_model if p_model > 0 else 999.0


def classify_level(p_model: float, ev: float, has_value_flag: bool) -> int:
    """
    Clasifica en niveles:
    1 = Máximo valor (P≥68% + EV>5% + value)
    2 = Intermedio (P≥62% + value)
    3 = Descartable
    """
    if p_model >= 0.68 and ev > 5.0 and has_value_flag:
        return 1
    elif p_model >= 0.62 and has_value_flag:
        return 2
    return 3   
