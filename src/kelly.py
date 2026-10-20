"""
Módulo de cálculo de Value Odds, Expected Value y Dimensionamiento de Posiciones
mediante el Criterio de Kelly para sistemas cuantitativos de inversión deportiva.
"""

from __future__ import annotations

import math
from enum import IntEnum
from typing import Final

try:
    from .config import BANKROLL_UNITS, KELLY_FRACTION
except ImportError:
    # Parámetros defensivos por defecto si no existe archivo de configuración
    KELLY_FRACTION: Final[float] = 0.25  # Fractional Kelly estándar para mitigación de varianza
    BANKROLL_UNITS: Final[float] = 100.0

# Constantes de seguridad cuantitativa
MAX_STAKE_PCT_CAP: Final[float] = 0.05  # Límite máximo del 5% del bankroll por operación unitaria
MIN_ACCEPTABLE_ODDS: Final[float] = 1.0001
MAX_REASONABLE_ODDS: Final[float] = 1000.0


class InvestmentTier(IntEnum):
    """Clasificación de jerarquía de valor según perfil riesgo/retorno."""
    TIER_1 = 1  # Máxima asimetría estadística (Core investment)
    TIER_2 = 2  # Asimetría estadística media/alta (Secondary investment)
    DISCARD = 3  # Sin ventaja estadística o descartable (Edge nulo o negativo)


def _is_valid_probability(p: float) -> bool:
    """Valida si un valor pertenece al espacio de probabilidad [0.0, 1.0]."""
    return math.isfinite(p) and 0.0 <= p <= 1.0


def _is_valid_odds(odds: float) -> bool:
    """Valida cuotas decimales mayores a 1.0 y numéricamente consistentes."""
    return math.isfinite(odds) and odds > MIN_ACCEPTABLE_ODDS


def implied_probability(odds: float) -> float:
    """
    Calcula la probabilidad implícita de una cuota decimal libre de sesgos de tipo infinito/NaN.
    
    Args:
        odds: Cuota decimal (European odds).
        
    Returns:
        Probabilidad implícita en [0.0, 1.0). Retorna 0.0 ante cuotas no operables.
    """
    if not _is_valid_odds(odds):
        return 0.0
    return 1.0 / odds


def has_value(p_model: float, odds: float, margin: float = 0.03) -> bool:
    """
    Determina si existe 'Value' superando el margen de seguridad (Edge mínimo exigido).
    
    Args:
        p_model: Probabilidad estimada por el modelo cuantitativo.
        odds: Cuota decimal del mercado.
        margin: Margen de seguridad sobre la probabilidad implícita (hurdle rate).
        
    Returns:
        True si p_model > p_implied + margin con datos válidos; False en caso contrario.
    """
    if not _is_valid_probability(p_model) or not _is_valid_odds(odds):
        return False
    if not math.isfinite(margin) or margin < 0.0:
        margin = 0.0

    p_implied = 1.0 / odds
    return p_model > (p_implied + margin)


def ev_percent(p_model: float, odds: float) -> float:
    """
    Calcula el Valor Esperado porcentual (EV% / ROI proyectado).
    
    E(Y) = (p * b - q) / 1.0 = p * odds - 1.0
    
    Args:
        p_model: Probabilidad estimada por el modelo [0.0, 1.0].
        odds: Cuota decimal del mercado.
        
    Returns:
        Retorno esperado en porcentaje (ej. 5.5 para un 5.5% de EV).
        Retorna -100.0 si los parámetros son inválidos.
    """
    if not _is_valid_probability(p_model) or not _is_valid_odds(odds):
        return -100.0

    ev = (p_model * odds) - 1.0
    return ev * 100.0


def kelly_stake(
    p_model: float,
    odds: float,
    fraction: float = KELLY_FRACTION,
    bankroll: float = BANKROLL_UNITS,
    max_cap_pct: float = MAX_STAKE_PCT_CAP,
) -> float:
    """
    Calcula el tamaño óptimo de la posición (stake) usando el Criterio de Kelly Fraccional
    con control estricto de drawdown y caps de preservación de capital.
    
    Fórmula de Kelly:
        f* = (b * p - q) / b = (p * odds - 1) / (odds - 1)
        
    Args:
        p_model: Probabilidad estimada del evento [0.0, 1.0].
        odds: Cuota decimal > 1.0.
        fraction: Factor de escala conservador (ej. 0.25 para Quarter-Kelly).
        bankroll: Tamaño total de la banca en unidades operativas.
        max_cap_pct: Exposición máxima individual permitida como fracción de la banca.
        
    Returns:
        Stake óptimo expresado en unidades. Retorna 0.0 si el Edge es nulo o negativo.
    """
    if not _is_valid_probability(p_model) or not _is_valid_odds(odds):
        return 0.0
    if not math.isfinite(fraction) or fraction <= 0.0:
        return 0.0
    if not math.isfinite(bankroll) or bankroll <= 0.0:
        return 0.0

    b = odds - 1.0
    # Kelly óptimo no restringido
    f_star = ((p_model * odds) - 1.0) / b

    # Si f_star <= 0, la esperanza matemática no justifica asignación de capital
    if f_star <= 0.0:
        return 0.0

    # Probabilidad límite superior para evitar sobrerriesgo
    f_star = min(f_star, 1.0)

    # Aplicación de Kelly Fraccional
    scaled_fraction = f_star * fraction

    # Techo de asignación estricto (Risk Management Guardrail)
    effective_cap = min(max_cap_pct, 1.0) if math.isfinite(max_cap_pct) and max_cap_pct > 0.0 else 1.0
    final_fraction = min(scaled_fraction, effective_cap)

    return round(final_fraction * bankroll, 4)


def breakeven_odds(p_model: float) -> float:
    """
    Calcula la cuota justa o cuota de punto de equilibrio (Fair/Breakeven Odds).
    
    Args:
        p_model: Probabilidad estimada por el modelo.
        
    Returns:
        Cuota decimal de indiferencia (1 / p). Retorna inf si p <= 0 o inválido.
    """
    if not _is_valid_probability(p_model) or p_model <= 0.0:
        return float("inf")
    
    odds = 1.0 / p_model
    return min(odds, MAX_REASONABLE_ODDS)


def classify_level(p_model: float, ev: float, has_value_flag: bool) -> int:
    """
    Clasifica la oportunidad de inversión en niveles jerárquicos cuantitativos.
    
    Criterios:
        - Tier 1: P_model >= 68%, EV >= 5.0% y has_value_flag activo.
        - Tier 2: P_model >= 62% y has_value_flag activo (con EV positivo residual).
        - Tier 3: Descartable (sin edge suficiente, varianza excesiva o flags negativos).
        
    Args:
        p_model: Probabilidad del modelo [0.0, 1.0].
        ev: Valor esperado en porcentaje (ej. 5.2 para 5.2%).
        has_value_flag: Bandera booleana de verificación de valor.
        
    Returns:
        Representación entera del nivel: 1 (Alto), 2 (Intermedio), 3 (Descartado).
    """
    if not has_value_flag or not _is_valid_probability(p_model) or not math.isfinite(ev):
        return InvestmentTier.DISCARD.value

    if p_model >= 0.68 and ev >= 5.0:
        return InvestmentTier.TIER_1.value
    elif p_model >= 0.62 and ev > 0.0:
        return InvestmentTier.TIER_2.value

    return InvestmentTier.DISCARD.value