"""
Métricas empíricas ponderadas en el tiempo y evaluación cualitativa de contexto.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any
from ..api_client import safe_score, team_id_from_match
from ..config import MIN_CONTEXT_SCORE


def _to_float(val: Any) -> float | None:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def compute_team_ratings(
    recent_matches: list[dict],
    target_team_id: str,
    stats_cache: dict[str, dict],
    league_avg_goals: float = 2.65,
) -> tuple[float, float, dict]:
    """
    Calcula fuerza de ataque/defensa ajustada por rival y decaimiento temporal.
    Retorna (att_strength, def_strength, stats_dict).
    """
    if not recent_matches or not target_team_id:
        return 1.0, 1.0, {}

    base_lam = league_avg_goals / 2.0
    weighted_xg_for = 0.0
    weighted_xg_against = 0.0
    total_weights = 0.0
    btts_count = 0
    clean_sheets = 0
    valid_matches = 0
    last_date: datetime | None = None

    for idx, m in enumerate(recent_matches):
        if not isinstance(m, dict):
            continue
        hid = team_id_from_match(m, "home")
        aid = team_id_from_match(m, "away")
        is_home = (hid == target_team_id)
        is_away = (aid == target_team_id)
        if not (is_home or is_away):
            continue

        sh = safe_score(m, "home")
        sa = safe_score(m, "away")
        if sh is None or sa is None:
            continue

        # Decaimiento temporal exponencial (partidos recientes pesan más)
        weight = math.exp(-0.08 * idx)

        my_goals = sh if is_home else sa
        opp_goals = sa if is_home else sh

        # Extraer xG real del partido si está disponible
        mid = m.get("id")
        st = stats_cache.get(mid, {}) if mid else {}
        my_xg = None
        opp_xg = None

        if st:
            overview = st.get("overview") or {}
            xg_block = (overview.get("expected_goals") or {}).get("all") or {}
            h_xg = _to_float(xg_block.get("home"))
            a_xg = _to_float(xg_block.get("away"))
            if h_xg is not None and a_xg is not None:
                my_xg = h_xg if is_home else a_xg
                opp_xg = a_xg if is_home else h_xg

        # Si no hay xG, fallback al gol real
        eff_for = my_xg if my_xg is not None else float(my_goals)
        eff_against = opp_xg if opp_xg is not None else float(opp_goals)

        weighted_xg_for += eff_for * weight
        weighted_xg_against += eff_against * weight
        total_weights += weight
        valid_matches += 1

        if my_goals > 0 and opp_goals > 0:
            btts_count += 1
        if opp_goals == 0:
            clean_sheets += 1

        utc = m.get("utc_date")
        if utc:
            try:
                dt = datetime.fromisoformat(str(utc).replace("Z", "+00:00"))
                if last_date is None or dt > last_date:
                    last_date = dt
            except Exception:
                pass

    if valid_matches == 0 or total_weights == 0:
        return 1.0, 1.0, {}

    avg_for = weighted_xg_for / total_weights
    avg_against = weighted_xg_against / total_weights

    att_strength = max(0.40, min(2.50, avg_for / base_lam))
    def_strength = max(0.40, min(2.50, avg_against / base_lam))

    stats = {
        "matches_count": valid_matches,
        "avg_xg_for": round(avg_for, 2),
        "avg_xg_against": round(avg_against, 2),
        "btts_rate": round(btts_count / valid_matches, 2),
        "clean_sheet_rate": round(clean_sheets / valid_matches, 2),
        "last_match_date": last_date,
    }

    return att_strength, def_strength, stats


def compute_h2h_metrics(h2h_matches: list[dict]) -> dict:
    if not h2h_matches:
        return {}
    total = 0
    over25 = 0
    btts = 0
    for m in h2h_matches[:6]:
        sh = safe_score(m, "home")
        sa = safe_score(m, "away")
        if sh is not None and sa is not None:
            total += 1
            if sh + sa > 2.5:
                over25 += 1
            if sh > 0 and sa > 0:
                btts += 1
    if total == 0:
        return {}
    return {
        "sample": total,
        "over25_rate": round(over25 / total, 2),
        "btts_rate": round(btts / total, 2),
    }


def evaluate_context_score(
    home_stats: dict,
    away_stats: dict,
    h2h: dict,
    home_injuries: dict,
    away_injuries: dict,
    market_key: str,
) -> tuple[float, list[str]]:
    """Calcula score de contexto (0-100) específico para cada tipo de mercado."""
    score = 50.0
    reasons: list[str] = []

    h_abs = len(home_injuries.get("injuries") or []) + len(home_injuries.get("suspensions") or [])
    a_abs = len(away_injuries.get("injuries") or []) + len(away_injuries.get("suspensions") or [])

    if "over" in market_key or "btts_yes" in market_key:
        if home_stats.get("avg_xg_for", 0) >= 1.50 and away_stats.get("avg_xg_for", 0) >= 1.30:
            score += 10
            reasons.append("Alto poder ofensivo mutuo")
        if home_stats.get("avg_xg_against", 0) >= 1.30 and away_stats.get("avg_xg_against", 0) >= 1.30:
            score += 8
            reasons.append("Defensas permeables")
        if h2h.get("over25_rate", 0) >= 0.65:
            score += 6
            reasons.append(f"H2H Over {h2h['over25_rate']:.0%}")

    elif "under" in market_key or "btts_no" in market_key:
        if home_stats.get("clean_sheet_rate", 0) >= 0.40 or away_stats.get("clean_sheet_rate", 0) >= 0.40:
            score += 10
            reasons.append("Alta tasa de porterías a cero")
        if home_stats.get("avg_xg_against", 0) <= 0.95:
            score += 8
            reasons.append("Solidez defensiva local")

    elif "home_win" in market_key or "dc_1x" in market_key or "home_dnb" in market_key:
        if a_abs >= 3:
            score += 8
            reasons.append(f"Visitante con {a_abs} bajas")
        if h_abs >= 3:
            score -= 10
            reasons.append(f"Local con {h_abs} bajas")

    elif "away_win" in market_key or "dc_x2" in market_key or "away_dnb" in market_key:
        if h_abs >= 3:
            score += 8
            reasons.append(f"Local con {h_abs} bajas")
        if a_abs >= 3:
            score -= 10
            reasons.append(f"Visitante con {a_abs} bajas")

    # Días de descanso
    now = datetime.now(timezone.utc)
    for side, stats in [("Local", home_stats), ("Visitante", away_stats)]:
        lmd = stats.get("last_match_date")
        if lmd:
            days = (now - lmd).total_seconds() / 86400.0
            if days < 2.5:
                score -= 8
                reasons.append(f"{side} con descanso < 3 días")

    return max(0.0, min(100.0, round(score, 1))), reasons
