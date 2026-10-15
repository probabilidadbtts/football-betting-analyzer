"""
Modelo Poisson / Dixon-Coles para probabilidad BTTS.
"""
import math
from .config import POISSON_MAX_GOALS


def poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def p_btts(lambda_home: float, lambda_away: float) -> float:
    """P(BTTS SÍ) = 1 - e^(-λh) - e^(-λa) + e^(-λh-λa)"""
    p_home_0 = math.exp(-lambda_home)
    p_away_0 = math.exp(-lambda_away)
    return 1.0 - p_home_0 - p_away_0 + p_home_0 * p_away_0


def p_over_2_5(lambda_home: float, lambda_away: float) -> float:
    lam_total = lambda_home + lambda_away
    p = sum(poisson_pmf(k, lam_total) for k in range(3))
    return 1.0 - p


def dixon_coles_correction(lambda_home: float, lambda_away: float,
                           rho: float = -0.1) -> float:
    """
    P(BTTS) con corrección Dixon-Coles para scores bajos.
    rho < 0 → reduce 0-0 y 1-1 → BTTS aumenta.
    """
    p_base = p_btts(lambda_home, lambda_away)

    # Probabilidades de scores bajos
    p_00 = poisson_pmf(0, lambda_home) * poisson_pmf(0, lambda_away)
    p_11 = poisson_pmf(1, lambda_home) * poisson_pmf(1, lambda_away)

    # Ajuste neto: si rho < 0, 0-0 y 1-1 disminuyen → BTTS sube
    adjustment = -rho * (p_00 + p_11)

    return min(0.99, max(0.01, p_base + adjustment))   
