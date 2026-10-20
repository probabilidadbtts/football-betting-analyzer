"""
Módulo de análisis cuantitativo y valoración de mercados deportivos.
Integra estimación bayesiana/xG, modelado bivariado de Poisson y cálculo
de edge/criterio de Kelly con protección de drawdown.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Dict, Final, List, Mapping, Optional, Tuple, TypedDict

from .api_client import team_id_from_match, team_name_from_match
from .config import DEFAULT_LEAGUE_AVG_GOALS, MARKETS, MIN_MATCHES_FOR_RATING
from .filters.context import (
    compute_h2h_metrics,
    compute_injury_impact,
    compute_side_ratings,
    evaluate_context_score,
)
from .markets.extractor import extract_and_devig_markets
from .markets.value import blend_discrete_distribution, evaluate_bet_value
from .models.poisson import compute_model_probs

log = logging.getLogger(__name__)

# Constantes numéricas de estabilidad y control de riesgo
EPSILON: Final[float] = 1e-9
MAX_VALID_ODDS: Final[float] = 1000.0
MIN_VALID_ODDS: Final[float] = 1.001
MAX_VALUE_LEVEL: Final[int] = 2


class ValuePick(TypedDict):
    market: str
    market_label: str
    odds: float
    bookmaker: str
    p_model: Optional[float]
    p_fair_market: Optional[float]
    p_final: float
    edge: float
    ev: float
    level: int
    stake: float
    context_score: float
    context_reasons: List[str]


class AnalysisResult(TypedDict):
    match_id: str
    home: str
    away: str
    is_live: bool
    minute: int
    score_str: Optional[str]
    lambda_home: float
    lambda_away: float
    value_picks: List[ValuePick]
    has_value: bool
    home_xg_matches: int
    away_xg_matches: int
    home_avg_xg_for: Optional[float]
    away_avg_xg_for: Optional[float]
    home_injury_impact: float
    away_injury_impact: float


def _validate_numeric(val: Any, default: float = 0.0) -> float:
    """Valida y coacciona valores flotantes finitos, previniendo NaN o Inf."""
    if val is None:
        return default
    try:
        f = float(val)
        return f if math.isfinite(f) else default
    except (ValueError, TypeError):
        return default


def _normalize_discrete_group(probs: Mapping[str, float], keys: List[str]) -> Dict[str, float]:
    """
    Garantiza consistencia axiomática de Kolmogorov: la suma del espacio muestral debe ser 1.0.
    """
    total = sum(max(0.0, _validate_numeric(probs.get(k))) for k in keys)
    if total <= EPSILON:
        uniform = 1.0 / len(keys)
        return {k: uniform for k in keys}
    return {k: max(0.0, _validate_numeric(probs.get(k))) / total for k in keys}


def analyze_match(
    match: Optional[Mapping[str, Any]],
    odds_payload: Optional[Mapping[str, Any]],
    home_home_matches: Optional[List[Dict[str, Any]]],
    away_away_matches: Optional[List[Dict[str, Any]]],
    home_injuries: Optional[Dict[str, Any]] = None,
    away_injuries: Optional[Dict[str, Any]] = None,
    home_squad: Optional[List[Dict[str, Any]]] = None,
    away_squad: Optional[List[Dict[str, Any]]] = None,
    h2h_matches: Optional[List[Dict[str, Any]]] = None,
    is_live: bool = False,
    minute: int = 0,
    current_home_goals: int = 0,
    current_away_goals: int = 0,
) -> Optional[AnalysisResult]:
    """
    Ejecuta el pipeline completo de tarificación cuantitativa, ajuste contextual y detección de valor.

    Returns:
        AnalysisResult con picks EV+ ordenados por ratio Sharpe/edge o None si no es computable.
    """
    if not match or not isinstance(match, Mapping):
        log.warning("Payload 'match' no proporcionado o estructurado incorrectamente.")
        return None

    try:
        match_id = str(match.get("id") or "").strip()
        if not match_id:
            log.warning("Match carece de identificador único ('id').")
            return None

        home = team_name_from_match(match, "home")
        away = team_name_from_match(match, "away")
        home_id = team_id_from_match(match, "home")
        away_id = team_id_from_match(match, "away")

        if not home or not away:
            log.warning("[%s] Metadatos de equipos incompletos: Home='%s', Away='%s'", match_id, home, away)
            return None

        # 1. Extracción y desmargenación del mercado (Fair Odds sintéticas)
        if not odds_payload:
            return None

        best_odds, fair_market_probs = extract_and_devig_markets(odds_payload)
        if not best_odds or not fair_market_probs:
            return None

        # 2. Análisis fundamental xG por factor de localía/visitante
        h_matches = home_home_matches if isinstance(home_home_matches, list) else []
        a_matches = away_away_matches if isinstance(away_away_matches, list) else []

        h_att, h_def, h_stats = compute_side_ratings(h_matches, home_id, is_home_side=True)
        a_att, a_def, a_stats = compute_side_ratings(a_matches, away_id, is_home_side=False)

        h_xg_count = int(h_stats.get("xg_matches", 0))
        a_xg_count = int(a_stats.get("xg_matches", 0))

        if h_xg_count < MIN_MATCHES_FOR_RATING or a_xg_count < MIN_MATCHES_FOR_RATING:
            log.debug("[%s] Muestra xG insuficiente: Home=%d, Away=%d", match_id, h_xg_count, a_xg_count)
            return None

        # 3. Ajustes de contexto extrínseco (bajas, lesiones, dinámicas H2H)
        h_impact, h_reasons, _ = compute_injury_impact(home_injuries or {}, home_squad or [])
        a_impact, a_reasons, _ = compute_injury_impact(away_injuries or {}, away_squad or [])
        h2h = compute_h2h_metrics(h2h_matches or [])

        # 4. Inferencia probabilística con corrección temporal in-play
        model_probs, lh, la = compute_model_probs(
            home_att=max(0.01, _validate_numeric(h_att, 1.0)),
            home_def=max(0.01, _validate_numeric(h_def, 1.0)),
            away_att=max(0.01, _validate_numeric(a_att, 1.0)),
            away_def=max(0.01, _validate_numeric(a_def, 1.0)),
            league_avg=max(0.5, _validate_numeric(DEFAULT_LEAGUE_AVG_GOALS, 2.7)),
            is_live=is_live,
            minute=max(0, min(120, int(minute))),
            current_home_goals=max(0, int(current_home_goals)),
            current_away_goals=max(0, int(current_away_goals)),
        )

        if not model_probs or lh < 0.0 or la < 0.0:
            log.error("[%s] Fallo en la convergencia del modelo Poisson. Lambdas: LH=%.2f, LA=%.2f", match_id, lh, la)
            return None

        # 5. Ensamble de distribuciones (Bayesian Market Blending)
        blended_1x2 = blend_discrete_distribution(model_probs, fair_market_probs, ["home_win", "draw", "away_win"])
        blended_totals = blend_discrete_distribution(model_probs, fair_market_probs, ["over_25", "under_25"])
        blended_btts = blend_discrete_distribution(model_probs, fair_market_probs, ["btts_yes", "btts_no"])

        norm_1x2 = _normalize_discrete_group(blended_1x2, ["home_win", "draw", "away_win"])
        norm_totals = _normalize_discrete_group(blended_totals, ["over_25", "under_25"])
        norm_btts = _normalize_discrete_group(blended_btts, ["btts_yes", "btts_no"])

        final_probs: Dict[str, float] = {**norm_1x2, **norm_totals, **norm_btts}

        # 6. Mercados sintéticos derivados sin redondeo prematuro
        ph = final_probs["home_win"]
        pd = final_probs["draw"]
        pa = final_probs["away_win"]

        final_probs["dc_1x"] = min(1.0, ph + pd)
        final_probs["dc_x2"] = min(1.0, pd + pa)
        final_probs["dc_12"] = min(1.0, ph + pa)

        nd = ph + pa
        if nd > EPSILON:
            final_probs["home_dnb"] = ph / nd
            final_probs["away_dnb"] = pa / nd
        else:
            final_probs["home_dnb"] = 0.5
            final_probs["away_dnb"] = 0.5

        # 7. Evaluación de valor esperado y dimensionamiento de postura (Kelly)
        picks: List[ValuePick] = []
        for m_key, m_label in MARKETS.items():
            if m_key not in best_odds:
                continue

            odds_data = best_odds[m_key]
            if not isinstance(odds_data, (tuple, list)) or len(odds_data) != 2:
                continue

            raw_b_odds, bk_name = odds_data
            b_odds = _validate_numeric(raw_b_odds, 0.0)

            if not (MIN_VALID_ODDS <= b_odds <= MAX_VALID_ODDS):
                continue

            p_final = final_probs.get(m_key)
            if p_final is None or not (0.0 <= p_final <= 1.0):
                continue

            p_fair = fair_market_probs.get(m_key)
            if p_fair is not None:
                p_fair = _validate_numeric(p_fair)
                if not (0.0 <= p_fair <= 1.0):
                    p_fair = None

            ctx_score, ctx_reasons = evaluate_context_score(
                home_stats=h_stats,
                away_stats=a_stats,
                h2h=h2h,
                home_injury_impact=h_impact,
                away_injury_impact=a_impact,
                home_injury_reasons=h_reasons,
                away_injury_reasons=a_reasons,
                market_key=m_key,
            )

            val = evaluate_bet_value(
                p_final=p_final,
                p_fair=p_fair,
                b_odds=b_odds,
                context_score=ctx_score,
            )

            if not isinstance(val, dict):
                continue

            has_value = bool(val.get("has_value", False))
            level = int(val.get("level", 99))
            stake = _validate_numeric(val.get("stake", 0.0))
            edge = _validate_numeric(val.get("edge", 0.0))
            ev = _validate_numeric(val.get("ev", 0.0))

            if has_value and level <= MAX_VALUE_LEVEL and stake > 0.0 and edge > 0.0:
                p_model_raw = model_probs.get(m_key)
                p_model = round(float(p_model_raw), 4) if p_model_raw is not None else None

                picks.append({
                    "market": str(m_key),
                    "market_label": str(m_label),
                    "odds": round(b_odds, 3),
                    "bookmaker": str(bk_name),
                    "p_model": p_model,
                    "p_fair_market": round(p_fair, 4) if p_fair is not None else None,
                    "p_final": round(p_final, 4),
                    "edge": round(edge, 4),
                    "ev": round(ev, 4),
                    "level": level,
                    "stake": round(stake, 4),
                    "context_score": round(_validate_numeric(ctx_score), 3),
                    "context_reasons": list(ctx_reasons) if isinstance(ctx_reasons, list) else [],
                })

        picks.sort(key=lambda x: (x["level"], -x["edge"], -x["ev"]))

        return {
            "match_id": match_id,
            "home": str(home),
            "away": str(away),
            "is_live": bool(is_live),
            "minute": int(minute),
            "score_str": f"{int(current_home_goals)}-{int(current_away_goals)}" if is_live else None,
            "lambda_home": round(lh, 3),
            "lambda_away": round(la, 3),
            "value_picks": picks,
            "has_value": len(picks) > 0,
            "home_xg_matches": h_xg_count,
            "away_xg_matches": a_xg_count,
            "home_avg_xg_for": round(float(h_stats["avg_xg_for"]), 3) if h_stats.get("avg_xg_for") is not None else None,
            "away_avg_xg_for": round(float(a_stats["avg_xg_for"]), 3) if a_stats.get("avg_xg_for") is not None else None,
            "home_injury_impact": round(_validate_numeric(h_impact), 3),
            "away_injury_impact": round(_validate_numeric(a_impact), 3),
        }

    except Exception:
        log.exception("Error crítico durante el análisis del match ID: %s", match.get("id"))
        return None