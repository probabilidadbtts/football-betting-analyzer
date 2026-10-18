"""
Modelo Poisson + Dixon-Coles completo.
Genera matriz de scores y deriva probabilidades de cualquier mercado.
"""
from __future__ import annotations

import math
from ..config import POISSON_MAX_GOALS, DIXON_COLES_RHO, HOME_ADVANTAGE


def _poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    try:
        return math.exp(k * math.log(lam) - lam - math.lgamma(k + 1))
    except (ValueError, OverflowError):
        return 0.0


def _tau(i: int, j: int, lambda_h: float, lambda_a: float, rho: float) -> float:
    """Factor de corrección Dixon-Coles para scores bajos."""
    if i == 0 and j == 0:
        return 1.0 - lambda_h * lambda_a * rho
    if i == 0 and j == 1:
        return 1.0 + lambda_h * rho
    if i == 1 and j == 0:
        return 1.0 + lambda_a * rho
    if i == 1 and j == 1:
        return 1.0 - rho
    return 1.0


def score_matrix(
    lambda_home: float,
    lambda_away: float,
    max_goals: int = POISSON_MAX_GOALS,
    rho: float = DIXON_COLES_RHO,
) -> list[list[float]]:
    """Matriz P(home=i, away=j) con corrección Dixon-Coles. Normalizada."""
    matrix = [[0.0] * (max_goals + 1) for _ in range(max_goals + 1)]
    total = 0.0
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            p = _poisson_pmf(i, lambda_home) * _poisson_pmf(j, lambda_away)
            p *= _tau(i, j, lambda_home, lambda_away, rho)
            p = max(0.0, p)
            matrix[i][j] = p
            total += p

    if total > 0:
        for i in range(max_goals + 1):
            for j in range(max_goals + 1):
                matrix[i][j] /= total
    return matrix


def market_probs(matrix: list[list[float]]) -> dict[str, float]:
    """Deriva todas las probabilidades de mercado desde la matriz de scores."""
    n = len(matrix)
    p = {
        "btts_yes": 0.0, "btts_no": 0.0,
        "over_25": 0.0, "under_25": 0.0,
        "home_win": 0.0, "draw": 0.0, "away_win": 0.0,
        "home_dnb": 0.0, "away_dnb": 0.0,
        "dc_1x": 0.0, "dc_12": 0.0, "dc_x2": 0.0,
    }

    for i in range(n):
        for j in range(n):
            prob = matrix[i][j]
            total_goals = i + j

            if i > 0 and j > 0:
                p["btts_yes"] += prob
            else:
                p["btts_no"] += prob

            if total_goals > 2:
                p["over_25"] += prob
            else:
                p["under_25"] += prob

            if i > j:
                p["home_win"] += prob
            elif i == j:
                p["draw"] += prob
            else:
                p["away_win"] += prob

    p["dc_1x"] = p["home_win"] + p["draw"]
    p["dc_12"] = p["home_win"] + p["away_win"]
    p["dc_x2"] = p["draw"] + p["away_win"]

    no_draw = p["home_win"] + p["away_win"]
    if no_draw > 1e-9:
        p["home_dnb"] = p["home_win"] / no_draw
        p["away_dnb"] = p["away_win"] / no_draw
    else:
        p["home_dnb"] = p["away_dnb"] = 0.5

    for k in p:
        p[k] = min(0.995, max(0.005, p[k]))
    return p


def estimate_lambdas(
    home_xg_for: float,
    home_xg_against: float,
    away_xg_for: float,
    away_xg_against: float,
    league_avg: float = 1.35,
    home_adv: float = HOME_ADVANTAGE,
) -> tuple[float, float]:
    """Estima λ_home y λ_away combinando ataque/defensa y ventaja local."""
    att_home = home_xg_for / league_avg if league_avg > 0 else 1.0
    def_away = away_xg_against / league_avg if league_avg > 0 else 1.0
    att_away = away_xg_for / league_avg if league_avg > 0 else 1.0
    def_home = home_xg_against / league_avg if league_avg > 0 else 1.0

    att_home = max(0.4, min(2.5, att_home))
    def_away = max(0.4, min(2.5, def_away))
    att_away = max(0.4, min(2.5, att_away))
    def_home = max(0.4, min(2.5, def_home))

    lambda_h = league_avg * att_home * def_away + home_adv
    lambda_a = league_avg * att_away * def_home

    return max(0.15, min(4.5, lambda_h)), max(0.15, min(4.5, lambda_a))


def compute_model_probs(
    home_xg_for: float,
    home_xg_against: float,
    away_xg_for: float,
    away_xg_against: float,
    match_xg_home: float | None = None,
    match_xg_away: float | None = None,
    league_avg: float = 1.35,
) -> tuple[dict[str, float], float, float]:
    """Pipeline: lambdas → matriz → probs de mercado."""
    lh, la = estimate_lambdas(
        home_xg_for, home_xg_against,
        away_xg_for, away_xg_against,
        league_avg=league_avg,
    )

    if match_xg_home is not None and match_xg_away is not None:
        lh = 0.5 * lh + 0.5 * max(0.15, match_xg_home)
        la = 0.5 * la + 0.5 * max(0.15, match_xg_away)

    matrix = score_matrix(lh, la)
    probs = market_probs(matrix)
    return probs, lh, la
