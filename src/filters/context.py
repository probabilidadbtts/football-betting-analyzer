"""
Rendimiento medido con xG real.
- Local: últimos 5 partidos como LOCAL (solo los que tienen xG)
- Visitante: últimos 5 partidos como VISITANTE (solo los que tienen xG)
+ Impacto de bajas usando market_value y posición.
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
    Calcula fuerza de ataque/defensa SOLO con partidos del lado correcto
    y SOLO si tienen xG real en /stats.
    """
    if not side_matches or not target_team_id:
        return 1.0, 1.0, {"matches_count": 0, "xg_matches": 0}

    base_lam = league_avg_goals / 2.0
    w_xg_for = 0.0
    w_xg_against = 0.0
    total_w = 0.0
    valid_xg = 0
    btts = 0
    cs = 0
    wins = 0
    gf_list: list[float] = []
    ga_list: list[float] = []
    last_date = None

    for idx, m in enumerate(side_matches):
        if not isinstance(m, dict):
            continue

        hid = team_id_from_match(m, "home")
        aid = team_id_from_match(m, "away")
        is_home = hid == target_team_id
        is_away = aid == target_team_id
        if not (is_home or is_away):
            continue
        if is_home_side and not is_home:
            continue
        if not is_home_side and not is_away:
            continue

        sh = safe_score(m, "home")
        sa = safe_score(m, "away")
        if sh is None or sa is None:
            continue

        # xG real del partido
        mid = m.get("id")
        st = match_stats(mid) if mid else {}
        my_xg = opp_xg = None
        if st:
            xg_block = ((st.get("overview") or {}).get("expected_goals") or {}).get("all") or {}
            h_xg = _to_float(xg_block.get("home"))
            a_xg = _to_float(xg_block.get("away"))
            if h_xg is not None and a_xg is not None:
                my_xg = h_xg if is_home else a_xg
                opp_xg = a_xg if is_home else h_xg

        if my_xg is None or opp_xg is None:
            continue  # sin xG → no se usa para predecir

        weight = math.exp(-0.12 * idx)
        w_xg_for += my_xg * weight
        w_xg_against += opp_xg * weight
        total_w += weight
        valid_xg += 1

        my_goals = sh if is_home else sa
        opp_goals = sa if is_home else sh
        gf_list.append(float(my_goals))
        ga_list.append(float(opp_goals))
        if my_goals > 0 and opp_goals > 0:
            btts += 1
        if opp_goals == 0:
            cs += 1
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

    if valid_xg < MIN_MATCHES_FOR_RATING or total_w == 0:
        return 1.0, 1.0, {"matches_count": valid_xg, "xg_matches": valid_xg}

    avg_for = w_xg_for / total_w
    avg_against = w_xg_against / total_w
    att = max(0.45, min(2.40, avg_for / base_lam))
    deff = max(0.45, min(2.40, avg_against / base_lam))

    return att, deff, {
        "matches_count": valid_xg,
        "xg_matches": valid_xg,
        "avg_xg_for": round(avg_for, 2),
        "avg_xg_against": round(avg_against, 2),
        "btts_rate": round(btts / valid_xg, 2),
        "clean_sheet_rate": round(cs / valid_xg, 2),
        "win_rate": round(wins / valid_xg, 2),
        "last_match_date": last_date,
        "avg_goals_for": round(sum(gf_list) / len(gf_list), 2) if gf_list else 0,
        "avg_goals_against": round(sum(ga_list) / len(ga_list), 2) if ga_list else 0,
    }


def compute_injury_impact(injuries_data: dict, squad: list[dict]) -> tuple[float, list[str], int]:
    """Impacto de bajas cruzando player_id con market_value y posición."""
    if not injuries_data:
        return 0.0, [], 0
    inj = injuries_data.get("injuries") or []
    sus = injuries_data.get("suspensions") or []
    absent_ids = {i.get("player_id") for i in inj + sus if isinstance(i, dict) and i.get("active", True) and i.get("player_id")}
    if not absent_ids:
        return 0.0, [], 0

    squad_map = {p["id"]: p for p in squad if isinstance(p, dict) and p.get("id")}
    total_value = 0.0
    key_players = 0
    reasons = []
    for pid in absent_ids:
        p = squad_map.get(pid)
        if not p:
            continue
        name = p.get("short_name") or p.get("name") or pid
        pos = (p.get("position") or "").upper()
        mv = _to_float(p.get("market_value")) or 0.0
        total_value += mv
        if pos in ("F", "FW", "ST", "CF", "AM", "CAM", "LW", "RW") or mv >= 8_000_000:
            key_players += 1
            reasons.append(f"Baja clave: {name} ({pos or '?'})")
        elif mv >= 3_000_000:
            reasons.append(f"Baja: {name}")

    num = len(absent_ids)
    impact = min(100.0, key_players * 22 + num * 6 + total_value / 5_000_000)
    if num >= 4 and not reasons:
        reasons.append(f"{num} jugadores ausentes")
    return round(impact, 1), reasons[:4], num


def compute_h2h_metrics(h2h_matches: list[dict]) -> dict:
    if not h2h_matches:
        return {}
    total = over25 = btts = 0
    for m in h2h_matches[:8]:
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
    return {"sample": total, "over25_rate": round(over25 / total, 2), "btts_rate": round(btts / total, 2)}


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

    if "over" in market_key or "btts_yes" in market_key:
        if home_stats.get("avg_xg_for", 0) >= 1.50 and away_stats.get("avg_xg_for", 0) >= 1.30:
            score += 12
            reasons.append("Alto xG ofensivo mutuo (form home/away)")
        if home_stats.get("avg_xg_against", 0) >= 1.30 and away_stats.get("avg_xg_against", 0) >= 1.25:
            score += 8
            reasons.append("Defensas permeables (xG)")
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
            reasons.extend(away_injury_reasons[:2] or [f"Impacto bajas visitante {away_injury_impact:.0f}"])
        if home_injury_impact >= 35:
            score -= 14
            reasons.extend(home_injury_reasons[:2] or [f"Impacto bajas local {home_injury_impact:.0f}"])
        if home_stats.get("win_rate", 0) >= 0.55:
            score += 5
            reasons.append("Buen form local (últimos 5 en casa)")

    elif any(k in market_key for k in ("away_win", "dc_x2", "away_dnb")):
        if home_injury_impact >= 35:
            score += 12
            reasons.extend(home_injury_reasons[:2] or [f"Impacto bajas local {home_injury_impact:.0f}"])
        if away_injury_impact >= 35:
            score -= 14
            reasons.extend(away_injury_reasons[:2] or [f"Impacto bajas visitante {away_injury_impact:.0f}"])

    now = datetime.now(timezone.utc)
    for side, stats in [("Local", home_stats), ("Visitante", away_stats)]:
        lmd = stats.get("last_match_date")
        if lmd:
            days = (now - lmd).total_seconds() / 86400.0
            if days < 2.8:
                score -= 10
                reasons.append(f"{side} descanso < 3 días")

    if home_stats.get("xg_matches", 0) < 5 or away_stats.get("xg_matches", 0) < 5:
        score -= 8
        reasons.append("Muestra xG home/away limitada")

    return max(0.0, min(100.0, round(score, 1))), reasons
