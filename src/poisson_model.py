"""
Modelo Poisson / Dixon-Coles para probabilidad BTTS.
Genera matriz de scores completa → P(BTTS) exacta.
"""
import math
from .config import POISSON_MAX_GOALS


def poisson_pmf(k: int, lam: float) -> float:
    """P(X=k) para distribución de Poisson."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def score_matrix(lambda_home: float, lambda_away: float) -> list[list[float]]:
    """
    Matriz de probabilidades P(home=i, away=j) para i,j en [0, MAX].
    """
    matrix = []
    for i in range(POISSON_MAX_GOALS + 1):
        row = []
        for j in range(POISSON_MAX_GOALS + 1):
            row.append(poisson_pmf(i, lambda_home) * poisson_pmf(j, lambda_away))
        matrix.append(row)
    return matrix


def p_btts(lambda_home: float, lambda_away: float) -> float:
    """
    P(BTTS SÍ) = 1 - P(home=0) - P(away=0) + P(home=0 AND away=0)
    = 1 - e^(-λh) - e^(-λa) + e^(-λh-λa)
    """
    p_home_0 = math.exp(-lambda_home)
    p_away_0 = math.exp(-lambda_away)
    return 1.0 - p_home_0 - p_away_0 + p_home_0 * p_away_0


def p_over_2_5(lambda_home: float, lambda_away: float) -> float:
    """P(total goles > 2.5) = 1 - P(0) - P(1) - P(2)."""
    lam_total = lambda_home + lambda_away
    p = 0.0
    for k in range(3):  # 0, 1, 2
        p += poisson_pmf(k, lam_total)
    return 1.0 - p


def dixon_coles_correction(p_home: float, p_away: float,
                           lambda_home: float, lambda_away: float,
                           rho: float = -0.1) -> float:
    """
    Corrección Dixon-Coles para scores bajos (0-0, 1-0, 0-1, 1-1).
    rho < 0 → reduce probabilidad de 0-0 y 1-1 (más BTTS).
    rho > 0 → reduce probabilidad de 1-0 y 0-1 (menos BTTS).
    """
    tau_00 = 1.0 - lambda_home * lambda_away * rho
    tau_10 = 1.0 + lambda_away * rho
    tau_01 = 1.0 + lambda_home * rho
    tau_11 = 1.0 - rho

    # Ajustar probabilidades de scores bajos
    p_00 = poisson_pmf(0, lambda_home) * poisson_pmf(0, lambda_away) * tau_00
    p_10 = poisson_pmf(1, lambda_home) * poisson_pmf(0, lambda_away) * tau_10
    p_01 = poisson_pmf(0, lambda_home) * poisson_pmf(1, lambda_away) * tau_01
    p_11 = poisson_pmf(1, lambda_home) * poisson_pmf(1, lambda_away) * tau_11

    # P(BTTS) = 1 - P(home=0) - P(away=0) + P(0,0)
    # Con corrección:
    p_home_0_corrected = p_00 + p_01  # P(home=0) = P(0,0) + P(0,1) + ...
    # Simplificación: usar la fórmula directa con corrección
    p_btts_base = p_btts(lambda_home, lambda_away)
    # Ajuste neto de la corrección sobre BTTS:
    # Si rho < 0: 0-0 y 1-1 disminuyen → BTTS aumenta
    # Ajuste aproximado:
    adjustment = -rho * (p_00 + p_11)
    return min(0.99, max(0.01, p_btts_base + adjustment))   
