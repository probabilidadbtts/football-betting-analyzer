"""
Motor de análisis multi-mercado.
Combina Poisson/Dixon-Coles + cuotas de mercado + contexto + Kelly.
Devuelve lista de oportunidades rankeadas por edge real.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .config import (
    MARKETS, WEIGHT_POISSON, WEIGHT_MARKET, WEIGHT_FORM,
    LEAGUE_AVG_GOALS, MIN_CONTEXT_SCORE,
)
from .api_client import (
    team_id_from_match, team_name_from_match, safe_score,
)
from .models.poisson import compute_model_probs
from .markets.extractor import extract_all_odds, best_odds, market_implied_prob
from .markets.value import (
    blend_probs, edge, expected_value_pct, kelly_stake,
    has_value, classify_opportunity,
)
from .filters.context import (
    compute_team_metrics, compute_xg_metrics, h2h_stats,
    absence_impact, context_score, passes_hard_filters, rest_days,
)

log = logging.getLogger(__name__)


def _extract_match_xg(st: dict) -> tuple[float | None, float | None]:
    """Intenta sacar xG del partido actual (pre-match forecast o live)."""
    if not st:
        return None, None
    home_xg = away_xg = None
    if isinstance(st.get("home"), dict):
        try:
            home_xg = float(st["home"].get("xg"))
        except (TypeError, ValueError):
            pass
    if isinstance(st.get("away"), dict):
        try:
            away_xg = float(st["away"].get("xg"))
        except (TypeError, ValueError):
            pass
    if home_xg is None or away_xg is None:
        overview = st.get("overview") or {}
        xg_block = (overview.get("expected_goals") or {}).get("all") or {}
        if home_xg is None:
            try:
                home_xg = float(xg_block.get("home"))
            except (TypeError, ValueError):
                pass
        if away_xg is None:
            try:
                away_xg = float(xg_block.get("away"))
            except (TypeError, ValueError):
                pass
    return home_xg, away_xg


def analyze(
    match: dict,
    st: dict,
    od: dict,
    home_recent: list[dict],
    away_recent: list[dict],
    home_stats_cache: dict[str, dict],
    away_stats_cache: dict[str, dict],
    h2h_matches: list[dict] | None = None,
    home_injuries: dict | None = None,
    away_injuries: dict | None = None,
    lineups_data: dict | None = None,
) -> dict | None:
    """
    Analiza un partido completo en todos los mercados configurados.
    Retorna dict con info del partido, probs del modelo, lista de picks, etc.
    """
    home = team_name_from_match(match, "home")
    away = team_name_from_match(match, "away")
    home_id = team_id_from_match(match, "home")
    away_id = team_id_from_match(match, "away")
    match_id = match.get("id", "")

    # ── Métricas de equipos ──
    home_m = compute_team_metrics(home_recent, home_id)
    away_m = compute_team_metrics(away_recent, away_id)
    home_xg_for, home_xg_against = compute_xg_metrics(home_recent, home_id, home_stats_cache)
    away_xg_for, away_xg_against = compute_xg_metrics(away_recent, away_id, away_stats_cache)

    if home_m:
        home_xg_for = home_xg_for or home_m.get("goals_for_avg", 1.3)
        home_xg_against = home_xg_against or home_m.get("goals_against_avg", 1.3)
    if away_m:
        away_xg_for = away_xg_for or away_m.get("goals_for_avg", 1.3)
        away_xg_against = away_xg_against or away_m.get("goals_against_avg", 1.3)

    match_xg_h, match_xg_a = _extract_match_xg(st or {})

    # ── Modelo ──
    model_probs, lambda_h, lambda_a = compute_model_probs(
        home_xg_for, home_xg_against,
        away_xg_for, away_xg_against,
        match_xg_home=match_xg_h,
        match_xg_away=match_xg_a,
        league_avg=LEAGUE_AVG_GOALS / 2.0,
    )

    # ── Cuotas ──
    all_odds = extract_all_odds(od or {})
    if not any(all_odds.values()):
        log.debug("Sin cuotas extraíbles: %s vs %s", home, away)
        return None

    # ── Ausencias ──
    h_abs_count, h_abs_names = absence_impact(home_injuries or {})
    a_abs_count, a_abs_names = absence_impact(away_injuries or {})

    # ── H2H ──
    h2h = h2h_stats(h2h_matches or [])

    # ── Ajuste de forma ──
    form_adj = 0.0
    hw = home_m.get("wins", 0)
    aw = away_m.get("wins", 0)
    if hw >= 4 and home_xg_for >= 1.3:
        form_adj += 0.03
    if aw >= 4 and away_xg_for >= 1.3:
        form_adj += 0.03
    if h_abs_count >= 2:
        form_adj -= 0.02
    if a_abs_count >= 2:
        form_adj -= 0.02

    # ── Evaluar cada mercado ──
    picks: list[dict] = []
    for mkt_key, mkt_label in MARKETS.items():
        candidates = all_odds.get(mkt_key) or []
        if not candidates:
            continue

        best_od, best_bk = best_odds(candidates)
        if not best_od:
            continue

        p_mkt = market_implied_prob(candidates, top_n=3)
        p_pois = model_probs.get(mkt_key, 0.5)

        p_final = blend_probs(
            p_poisson=p_pois,
            p_market=p_mkt,
            form_adj=form_adj,
            weight_poisson=WEIGHT_POISSON,
            weight_market=WEIGHT_MARKET,
            weight_form=WEIGHT_FORM,
        )

        ctx, ctx_reasons = context_score(
            home_m, away_m,
            home_xg_for, home_xg_against,
            away_xg_for, away_xg_against,
            h2h,
            home_absences=h_abs_count,
            away_absences=a_abs_count,
            market_key=mkt_key,
        )

        e = edge(p_final, best_od)
        ev = expected_value_pct(p_final, best_od)
        value = has_value(p_final, best_od)
        level = classify_opportunity(p_final, best_od, ctx)
        stake = kelly_stake(p_final, best_od) if value else 0.0

        hard_ok, hard_reasons = passes_hard_filters(home_m, away_m, ctx)

        picks.append({
            "market": mkt_key,
            "market_label": mkt_label,
            "odds": best_od,
            "bookmaker": best_bk,
            "p_poisson": round(p_pois, 4),
            "p_market": round(p_mkt, 4) if p_mkt else None,
            "p_model": round(p_final, 4),
            "edge": round(e, 4),
            "ev": round(ev, 2),
            "value": value,
            "level": level,
            "stake": round(stake, 2),
            "context_score": round(ctx, 1),
            "context_reasons": ctx_reasons,
            "hard_filters_ok": hard_ok,
            "hard_reasons": hard_reasons,
        })

    value_picks = [
        p for p in picks
        if p["value"] and p["hard_filters_ok"] and p["level"] <= 2
    ]
    value_picks.sort(key=lambda x: (-x["level"] == 1, -x["edge"], -x["context_score"]))

    return {
        "match_id": match_id,
        "home": home,
        "away": away,
        "home_id": home_id,
        "away_id": away_id,
        "utc_date": match.get("utc_date"),
        "competition_id": match.get("competition_id"),
        "lambda_home": round(lambda_h, 3),
        "lambda_away": round(lambda_a, 3),
        "home_xg_for": round(home_xg_for, 3),
        "home_xg_against": round(home_xg_against, 3),
        "away_xg_for": round(away_xg_for, 3),
        "away_xg_against": round(away_xg_against, 3),
        "home_btts_rate": round(home_m.get("btts_rate", 0), 3),
        "away_btts_rate": round(away_m.get("btts_rate", 0), 3),
        "home_cs_rate": round(home_m.get("clean_sheet_rate", 0), 3),
        "away_cs_rate": round(away_m.get("clean_sheet_rate", 0), 3),
        "h2h": h2h,
        "home_absences": h_abs_count,
        "away_absences": a_abs_count,
        "home_absence_names": h_abs_names,
        "away_absence_names": a_abs_names,
        "all_picks": picks,
        "value_picks": value_picks,
        "best_pick": value_picks[0] if value_picks else None,
        "has_value": len(value_picks) > 0,
            }
