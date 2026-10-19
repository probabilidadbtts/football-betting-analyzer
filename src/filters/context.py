"""
Form home/away específico + impacto real de bajas usando market_value y posición.
Solo usa partidos con xG disponible.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any
from ..api_client import safe_score, team_id_from_match, match_stats
from ..config import MIN_MATCHES_FOR_RATING


def _to_float(val: Any) -> float | None:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def compute_side_ratings(
    side_matches: list[dict],
    target_team_id: str,
    is_home_side: bool,
    league_avg_goals: float = 2.70,
) -> tuple[float, float, dict]:
    """
    Calcula att/def SOLO con partidos del lado correcto (local o visitante)
    y SOLO si tienen xG disponible.
    """
    if not side_matches or not target_team_id:
        return 1.0, 1.0, {"matches_count": 0, "xg_matches": 0}

    base_lam = league_avg_goals / 2.0
    weighted_xg_for = 0.0
    weighted_xg_against = 0.0
    total_weights = 0.0
    valid_xg = 0
    btts_count = 0
    clean_sheets = 0
    wins = 0
    goals_for_list: list[float] = []
    goals_against_list: list[float] = []
    last_date: datetime | None = None

    for idx, m in enumerate(side_matches):
        if not isinstance(m, dict):
            continue
        if not m.get("xg_available"):
            continue  # Solo partidos con historial xG

        hid = team_id_from_match(m, "home")
        aid = team_id_from_match(m, "away")
        is_home = (hid == target_team_id)
        is_away = (aid == target_team_id)
        if not (is_home or is_away):
            continue

        # Verificar que el lado coincide con lo pedido
        if is_home_side and not is_home:
            continue
        if not is_home_side and not is_away:
            continue

        sh = safe_score(m, "home")
        sa = safe_score(m, "away")
        if sh is None or sa is None:
            continue

        weight = math.exp(-0.12 * idx)  # más peso a los más recientes

        my_goals = sh if is_home else sa
        opp_goals = sa if is_home else sh

        # xG del partido
        mid = m.get("id")
        st = match_stats(mid) if mid else {}
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

        if my_xg is None or opp_xg is None:
            continue  # sin xG real → descartamos

        weighted_xg_for += my_xg * weight
        weighted_xg_against += opp_xg * weight
        total_weights += weight
        valid_xg += 1

        goals_for_list.append(float(my_goals))
        goals_against_list.append(float(opp_goals))

        if my_goals > 0 and opp_goals > 0:
            btts_count += 1
        if opp_goals == 0:
            clean_sheets += 1
        if my_goals > opp_goals:
            wins += 1

        utc = m.get("utc_date")
        if utc:
            try:
                dt = datetime.fromisoformat(str(utc).replace("Z", "+00:00"))
                if last_date is None or dt > last_date:
                    last_date = dt
            except Exception:
                pass

    if valid_xg < MIN_MATCHES_FOR_RATING or total_weights == 0:
        return 1.0, 1.0, {"matches_count": valid_xg, "xg_matches": valid_xg}

    avg_for = weighted_xg_for / total_weights
    avg_against = weighted_xg_against / total_weights

    att_strength = max(0.45, min(2.40, avg_for / base_lam))
    def_strength = max(0.45, min(2.40, avg_against / base_lam))

    stats = {
        "matches_count": valid_xg,
        "xg_matches": valid_xg,
        "avg_xg_for": round(avg_for, 2),
        "avg_xg_against": round(avg_against, 2),
        "btts_rate": round(btts_count / valid_xg, 2),
        "clean_sheet_rate": round(clean_sheets / valid_xg, 2),
        "win_rate": round(wins / valid_xg, 2),
        "last_match_date": last_date,
        "avg_goals_for": round(sum(goals_for_list) / len(goals_for_list), 2) if goals_for_list else 0,
        "avg_goals_against": round(sum(goals_against_list) / len(goals_against_list), 2) if goals_against_list else 0,
    }
    return att_strength, def_strength, stats


def compute_injury_impact(
    injuries_data: dict,
    squad: list[dict],
) -> tuple[float, list[str], int]:
    """
    Calcula impacto de bajas cruzando player_id con la plantilla.
    Usa market_value y posición.
    Retorna: (impact_score 0-100, reasons, num_absences)
    """
    if not injuries_data:
        return 0.0, [], 0

    inj_list = injuries_data.get("injuries") or []
    sus_list = injuries_data.get("suspensions") or []
    absent_ids = set()
    for item in inj_list + sus_list:
        if isinstance(item, dict) and item.get("active", True):
            pid = item.get("player_id")
            if pid:
                absent_ids.add(pid)

    if not absent_ids:
        return 0.0, [], 0

    # Mapa de plantilla
    squad_map = {}
    for p in squad:
        if isinstance(p, dict) and p.get("id"):
            squad_map[p["id"]] = p

    total_value = 0.0
    key_players = 0
    reasons = []
    for pid in absent_ids:
        player = squad_map.get(pid)
        if not player:
            continue
        name = player.get("short_name") or player.get("name") or pid
        pos = (player.get("position") or "").upper()
        mv = _to_float(player.get("market_value")) or 0.0

        total_value += mv
        # Posiciones clave
        if pos in ("F", "FW", "ST", "CF", "AM", "CAM", "LW", "RW") or mv >= 8_000_000:
            key_players += 1
            reasons.append(f"Baja clave: {name} ({pos or '?'})")
        elif mv >= 3_000_000:
            reasons.append(f"Baja: {name}")

    num_abs = len(absent_ids)
    # Score de impacto (0-100)
    impact = min(100.0, (key_players * 22) + (num_abs * 6) + (total_value / 5_000_000))
    if num_abs >= 4 and not reasons:
        reasons.append(f"{num_abs} jugadores ausentes")

    return round(impact, 1), reasons[:4], num_abs


def compute_h2h_metrics(h2h_matches: list[dict]) -> dict:
    if not h2h_matches:
        return {}
    total = 0
    over25 = 0
    btts = 0
    for m in h2h_matches[:8]:
        if not m.get("xg_available"):
            continue
        sh = safe_score(m, "home")
        sa = safe_score(m, "away")
        if sh is not None and sa is not None:
            total += 1
            if sh + sa > 2.5:
                over25 += 1
            if sh > 0 and sa > 0:
                btts += 1
    if total < 2:
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
    home_injury_impact: float,
    away_injury_impact: float,
    home_injury_reasons: list[str],
    away_injury_reasons: list[str],
    market_key: str,
) -> tuple[float, list[str]]:
    score = 52.0
    reasons: list[str] = []

    # Señales ofensivas / defensivas (solo con datos xG)
    if "over" in market_key or "btts_yes" in market_key:
        if home_stats.get("avg_xg_for", 0) >= 1.50 and away_stats.get("avg_xg_for", 0) >= 1.30:
            score += 12
            reasons.append("Alto poder ofensivo mutuo (xG home/away)")
        if home_stats.get("avg_xg_against", 0) >= 1.30 and away_stats.get("avg_xg_against", 0) >= 1.25:
            score += 8
            reasons.append("Defensas permeables")
        if h2h.get("over25_rate", 0) >= 0.70:
            score += 7
            reasons.append(f"H2H Over {h2h['over25_rate']:.0%}")

    elif "under" in market_key or "btts_no" in market_key:
        if home_stats.get("clean_sheet_rate", 0) >= 0.40 or away_stats.get("clean_sheet_rate", 0) >= 0.40:
            score += 11
            reasons.append("Alta tasa de porterías a cero")
        if home_stats.get("avg_xg_against", 0) <= 0.95 and away_stats.get("avg_xg_against", 0) <= 1.10:
            score += 9
            reasons.append("Solidez defensiva (xG)")

    elif any(k in market_key for k in ("home_win", "dc_1x", "home_dnb")):
        if away_injury_impact >= 35:
            score += 12
            reasons.extend(away_injury_reasons[:2] or [f"Impacto bajas visitante: {away_injury_impact:.0f}"])
        if home_injury_impact >= 35:
            score -= 14
            reasons.extend(home_injury_reasons[:2] or [f"Impacto bajas local: {home_injury_impact:.0f}"])
        if home_stats.get("win_rate", 0) >= 0.55:
            score += 5
            reasons.append("Buen form local (últimos 5 en casa)")

    elif any(k in market_key for k in ("away_win", "dc_x2", "away_dnb")):
        if home_injury_impact >= 35:
            score += 12
            reasons.extend(home_injury_reasons[:2] or [f"Impacto bajas local: {home_injury_impact:.0f}"])
        if away_injury_impact >= 35:
            score -= 14
            reasons.extend(away_injury_reasons[:2] or [f"Impacto bajas visitante: {away_injury_impact:.0f}"])

    # Fatiga
    now = datetime.now(timezone.utc)
    for side, stats in [("Local", home_stats), ("Visitante", away_stats)]:
        lmd = stats.get("last_match_date")
        if lmd:
            days = (now - lmd).total_seconds() / 86400.0
            if days < 2.8:
                score -= 10
                reasons.append(f"{side} con descanso < 3 días")

    # Muestra insuficiente
    if home_stats.get("xg_matches", 0) < 5 or away_stats.get("xg_matches", 0) < 5:
        score -= 8
        reasons.append("Muestra xG home/away limitada")

    return max(0.0, min(100.0, round(score, 1))), reasons
