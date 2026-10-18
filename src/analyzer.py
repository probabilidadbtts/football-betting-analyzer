"""
Motor analítico central: coordina modelo bivariado, desmargenación y valoración coherente.
"""
from __future__ import annotations

import logging
from .config import DEFAULT_LEAGUE_AVG_GOALS, MARKETS
from .api_client import (
    team_name_from_match, team_id_from_match,
)
from .models.poisson import compute_model_probs
from .markets.extractor import extract_and_devig_markets
from .markets.value import blend_discrete_distribution, evaluate_bet_value
from .filters.context import (
    compute_team_ratings, compute_h2h_metrics, evaluate_context_score,
)

log = logging.getLogger(__name__)


def analyze_match(
    match: dict,
    odds_payload: dict,
    home_recent: list[dict],
    away_recent: list[dict],
    home_stats_cache: dict[str, dict],
    away_stats_cache: dict[str, dict],
    h2h_matches: list[dict] | None = None,
    home_injuries: dict | None = None,
    away_injuries: dict | None = None,
    is_live: bool = False,
    minute: int = 0,
    current_home_goals: int = 0,
    current_away_goals: int = 0,
) -> dict | None:
    match_id = match.get("id", "")
    home = team_name_from_match(match, "home")
    away = team_name_from_match(match, "away")
    home_id = team_id_from_match(match, "home")
    away_id = team_id_from_match(match, "away")

    # 1. Extraer cuotas y calcular probabilidades sin margen (de-vigged)
    best_odds, fair_market_probs = extract_and_devig_markets(odds_payload or {})
    if not best_odds:
        return None

    # 2. Obtener fuerzas relativas
    h_att, h_def, h_stats = compute_team_ratings(home_recent, home_id, home_stats_cache)
    a_att, a_def, a_stats = compute_team_ratings(away_recent, away_id, away_stats_cache)

    if h_stats.get("matches_count", 0) < 4 or a_stats.get("matches_count", 0) < 4:
        return None

    h2h = compute_h2h_metrics(h2h_matches or [])

    # 3. Probabilidades del modelo matemático
    model_probs, lh, la = compute_model_probs(
        home_att=h_att,
        home_def=h_def,
        away_att=a_att,
        away_def=a_def,
        league_avg=DEFAULT_LEAGUE_AVG_GOALS,
        is_live=is_live,
        minute=minute,
        current_home_goals=current_home_goals,
        current_away_goals=current_away_goals,
    )

    # 4. Ensamble coherente por simplex de mercado
    blended_1x2 = blend_discrete_distribution(
        model_probs, fair_market_probs, ["home_win", "draw", "away_win"]
    )
    blended_totals = blend_discrete_distribution(
        model_probs, fair_market_probs, ["over_25", "under_25"]
    )
    blended_btts = blend_discrete_distribution(
        model_probs, fair_market_probs, ["btts_yes", "btts_no"]
    )

    final_probs: dict[str, float] = {}
    final_probs.update(blended_1x2)
    final_probs.update(blended_totals)
    final_probs.update(blended_btts)

    # Derivadas coherentes del 1X2 combinado
    ph, pd, pa = final_probs["home_win"], final_probs["draw"], final_probs["away_win"]
    final_probs["dc_1x"] = round(ph + pd, 4)
    final_probs["dc_x2"] = round(pd + pa, 4)
    final_probs["dc_12"] = round(ph + pa, 4)
    non_draw = ph + pa
    final_probs["home_dnb"] = round(ph / non_draw, 4) if non_draw > 0 else 0.5
    final_probs["away_dnb"] = round(pa / non_draw, 4) if non_draw > 0 else 0.5

    # 5. Evaluación individual de valor
    picks = []
    for m_key, m_label in MARKETS.items():
        if m_key not in best_odds:
            continue

        b_odds, bk_name = best_odds[m_key]
        p_final = final_probs[m_key]
        p_fair_mkt = fair_market_probs.get(m_key)

        ctx_score, ctx_reasons = evaluate_context_score(
            home_stats=h_stats,
            away_stats=a_stats,
            h2h=h2h,
            home_injuries=home_injuries or {},
            away_injuries=away_injuries or {},
            market_key=m_key,
        )

        val_res = evaluate_bet_value(
            prob_blended=p_final,
            fair_market_prob=p_fair_mkt,
            best_odds=b_odds,
            context_score=ctx_score,
        )

        if val_res["has_value"] and val_res["level"] <= 2:
            picks.append({
                "market": m_key,
                "market_label": m_label,
                "odds": b_odds,
                "bookmaker": bk_name,
                "p_model": model_probs[m_key],
                "p_fair_market": p_fair_mkt,
                "p_final": p_final,
                "edge": val_res["edge"],
                "ev": val_res["ev"],
                "level": val_res["level"],
                "stake": val_res["stake"],
                "context_score": ctx_score,
                "context_reasons": ctx_reasons,
            })

    picks.sort(key=lambda x: (x["level"], -x["edge"]))

    return {
        "match_id": match_id,
        "home": home,
        "away": away,
        "is_live": is_live,
        "minute": minute,
        "score_str": f"{current_home_goals}-{current_away_goals}" if is_live else None,
        "lambda_home": round(lh, 2),
        "lambda_away": round(la, 2),
        "value_picks": picks,
        "has_value": len(picks) > 0,
    }
