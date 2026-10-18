"""
Modelo de distribución bivariada Poisson y corrección Dixon-Coles calibrada.
Soporta decaimiento temporal y estado de partido en vivo.
"""
from __future__ import annotations

import math
from ..config import POISSON_MAX_GOALS, DIXON_COLES_RHO, HOME_ADVANTAGE_FACTOR


def poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    try:
        return math.exp(k * math.log(lam) - lam - math.lgamma(k + 1))
    except (ValueError, OverflowError):
        return 0.0


def _dixon_coles_tau(i: int, j: int, lh: float, la: float, rho: float) -> float:
    """Ajuste de covarianza para marcadores de baja frecuencia."""
    if i == 0 and j == 0:
        return max(0.0, 1.0 - (lh * la * rho))
    if i == 0 and j == 1:
        return max(0.0, 1.0 + (lh * rho))
    if i == 1 and j == 0:
        return max(0.0, 1.0 + (la * rho))
    if i == 1 and j == 1:
        return max(0.0, 1.0 - rho)
    return 1.0


def score_matrix(
    lambda_home: float,
    lambda_away: float,
    max_goals: int = POISSON_MAX_GOALS,
    rho: float = DIXON_COLES_RHO,
) -> list[list[float]]:
    """Calcula la matriz estocástica normalizada P(goles_local=i, goles_visitante=j)."""
    matrix = [[0.0] * (max_goals + 1) for _ in range(max_goals + 1)]
    total = 0.0

    for i in range(max_goals + 1):
        pi = poisson_pmf(i, lambda_home)
        for j in range(max_goals + 1):
            pj = poisson_pmf(j, lambda_away)
            tau = _dixon_coles_tau(i, j, lambda_home, lambda_away, rho)
            prob = pi * pj * tau
            matrix[i][j] = prob
            total += prob

    if total > 0.0:
        for i in range(max_goals + 1):
            for j in range(max_goals + 1):
                matrix[i][j] /= total

    return matrix


def market_probs_from_matrix(
    matrix: list[list[float]],
    current_home_goals: int = 0,
    current_away_goals: int = 0,
) -> dict[str, float]:
    """
    Deriva probabilidades para todos los mercados soportados.
    En partidos en vivo, suma los goles actuales a los goles proyectados restantes.
    """
    max_goals = len(matrix) - 1
    p = {
        "home_win": 0.0, "draw": 0.0, "away_win": 0.0,
        "over_25": 0.0, "under_25": 0.0,
        "btts_yes": 0.0, "btts_no": 0.0,
        "dc_1x": 0.0, "dc_12": 0.0, "dc_x2": 0.0,
        "home_dnb": 0.5, "away_dnb": 0.5,
    }

    for rem_h in range(max_goals + 1):
        for rem_a in range(max_goals + 1):
            prob = matrix[rem_h][rem_a]
            if prob <= 0:
                continue

            final_h = current_home_goals + rem_h
            final_a = current_away_goals + rem_a
            total_goals = final_h + final_a

            if final_h > final_a:
                p["home_win"] += prob
            elif final_h == final_a:
                p["draw"] += prob
            else:
                p["away_win"] += prob

            if total_goals > 2.5:
                p["over_25"] += prob
            else:
                p["under_25"] += prob

            if final_h > 0 and final_a > 0:
                p["btts_yes"] += prob
            else:
                p["btts_no"] += prob

    # Doble oportunidad coherente
    p["dc_1x"] = p["home_win"] + p["draw"]
    p["dc_x2"] = p["draw"] + p["away_win"]
    p["dc_12"] = p["home_win"] + p["away_win"]

    # Draw No Bet coherente
    non_draw_p = p["home_win"] + p["away_win"]
    if non_draw_p > 1e-6:
        p["home_dnb"] = p["home_win"] / non_draw_p
        p["away_dnb"] = p["away_win"] / non_draw_p

    # Normalizar valores entre [0.001, 0.999]
    return {k: max(0.001, min(0.999, round(v, 4))) for k, v in p.items()}


def estimate_lambdas(
    home_att_strength: float,
    home_def_strength: float,
    away_att_strength: float,
    away_def_strength: float,
    league_avg_goals: float = 2.65,
) -> tuple[float, float]:
    """Estima los parámetros de Poisson ajustados por ataque y defensa relativa."""
    base_lam = league_avg_goals / 2.0
    lam_h = base_lam * home_att_strength * away_def_strength * HOME_ADVANTAGE_FACTOR
    lam_a = base_lam * away_att_strength * home_def_strength

    return max(0.20, min(4.20, lam_h)), max(0.20, min(4.20, lam_a))


def compute_model_probs(
    home_att: float,
    home_def: float,
    away_att: float,
    away_def: float,
    league_avg: float = 2.65,
    is_live: bool = False,
    minute: int = 0,
    current_home_goals: int = 0,
    current_away_goals: int = 0,
) -> tuple[dict[str, float], float, float]:
    """Calcula las probabilidades del modelo teniendo en cuenta el tiempo restante."""
    lh_full, la_full = estimate_lambdas(home_att, home_def, away_att, away_def, league_avg)

    if not is_live:
        mat = score_matrix(lh_full, la_full)
        return market_probs_from_matrix(mat, 0, 0), lh_full, la_full

    # Ajuste para partido en vivo: decaimiento temporal lineal con cota mínima
    time_remaining_ratio = max(0.03, (90.0 - min(minute, 88)) / 90.0)
    lh_rem = lh_full * time_remaining_ratio
    la_rem = la_full * time_remaining_ratio

    mat = score_matrix(lh_rem, la_rem)
    probs = market_probs_from_matrix(mat, current_home_goals, current_away_goals)
    return probs, lh_rem, la_rem
