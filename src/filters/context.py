"""
Métricas de equipo + scoring contextual (soft filters).
En lugar de rechazar binariamente, se asigna un score 0-100.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..api_client import safe_score, team_id_from_match
from ..config import (
    BTTS_RATE_GOOD, XGA_SOFT_MIN, CLEAN_SHEET_SOFT_MAX,
    REST_DAYS_IDEAL, REST_DAYS_MIN, MIN_CONTEXT_SCORE,
)


def _f(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _d(v: Any) -> dict:
    return v if isinstance(v, dict) else {}


def compute_team_metrics(recent_matches: list[dict], team_id: str) -> dict:
    """BTTS rate, clean sheets, goles, última fecha, forma WDL."""
    if not recent_matches or not team_id:
        return {}

    total = 0
    btts = 0
    cs = 0
    goals_for = 0.0
    goals_against = 0.0
    wins = draws = losses = 0
    last_date: datetime | None = None

    for m in recent_matches:
        if not isinstance(m, dict):
            continue
        sh = safe_score(m, "home")
        sa = safe_score(m, "away")
        if sh is None or sa is None:
            continue

        hid = team_id_from_match(m, "home")
        aid = team_id_from_match(m, "away")
        is_home = hid == team_id
        is_away = aid == team_id
        if not (is_home or is_away):
            continue

        my_g = sh if is_home else sa
        opp_g = sa if is_home else sh

        total += 1
        goals_for += my_g
        goals_against += opp_g
        if my_g > 0 and opp_g > 0:
            btts += 1
        if opp_g == 0:
            cs += 1

        if my_g > opp_g:
            wins += 1
        elif my_g == opp_g:
            draws += 1
        else:
            losses += 1

        utc = m.get("utc_date") or m.get("date")
        if utc:
            try:
                d = datetime.fromisoformat(str(utc).replace("Z", "+00:00"))
                if last_date is None or d > last_date:
                    last_date = d
            except (ValueError, TypeError):
                pass

    if total == 0:
        return {}

    return {
        "matches": total,
        "btts_rate": btts / total,
        "clean_sheet_rate": cs / total,
        "goals_for_avg": goals_for / total,
        "goals_against_avg": goals_against / total,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "last_match_date": last_date,
        "points_per_game": (wins * 3 + draws) / total,
    }


def compute_xg_metrics(
    recent_matches: list[dict],
    team_id: str,
    stats_cache: dict[str, dict],
) -> tuple[float, float]:
    """Promedio xG for / xG against de los partidos recientes con stats."""
    xg_for: list[float] = []
    xg_against: list[float] = []

    for m in recent_matches:
        mid = m.get("id")
        if not mid or mid not in stats_cache:
            continue
        st = _d(stats_cache[mid])
        if not st:
            continue

        hid = team_id_from_match(m, "home")
        is_home = hid == team_id

        home_xg = None
        away_xg = None

        if isinstance(st.get("home"), dict):
            home_xg = _f(st["home"].get("xg"))
        if isinstance(st.get("away"), dict):
            away_xg = _f(st["away"].get("xg"))

        overview = _d(st.get("overview"))
        xg_block = _d(overview.get("expected_goals"))
        all_xg = _d(xg_block.get("all"))
        if home_xg is None:
            home_xg = _f(all_xg.get("home"))
        if away_xg is None:
            away_xg = _f(all_xg.get("away"))

        if is_home:
            if home_xg is not None:
                xg_for.append(home_xg)
            if away_xg is not None:
                xg_against.append(away_xg)
        else:
            if away_xg is not None:
                xg_for.append(away_xg)
            if home_xg is not None:
                xg_against.append(home_xg)

    xf = sum(xg_for) / len(xg_for) if xg_for else 1.25
    xa = sum(xg_against) / len(xg_against) if xg_against else 1.25
    return xf, xa


def rest_days(metrics: dict, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    last = metrics.get("last_match_date")
    if not last:
        return 7.0
    try:
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return max(0.0, (now - last).total_seconds() / 86400.0)
    except Exception:
        return 7.0


def h2h_stats(h2h_matches: list[dict]) -> dict:
    if not h2h_matches:
        return {}
    total = 0
    btts = 0
    over25 = 0
    for m in h2h_matches[:8]:
        sh = safe_score(m, "home")
        sa = safe_score(m, "away")
        if sh is None or sa is None:
            continue
        total += 1
        if sh > 0 and sa > 0:
            btts += 1
        if sh + sa > 2.5:
            over25 += 1
    if total == 0:
        return {}
    return {
        "matches": total,
        "btts_rate": btts / total,
        "over25_rate": over25 / total,
    }


def absence_impact(injuries_data: dict, key_positions: set[str] | None = None) -> tuple[int, list[str]]:
    """Cuenta jugadores clave lesionados/suspendidos."""
    key_positions = key_positions or {"F", "ST", "CF", "LW", "RW", "AM", "CAM"}
    names: list[str] = []
    count = 0
    for section in ("injuries", "suspensions"):
        for item in (injuries_data.get(section) or []):
            if not isinstance(item, dict):
                continue
            if item.get("active") is False:
                continue
            status = str(item.get("status", "")).lower()
            if status in ("out", "doubtful", "") or "suspension" in section:
                count += 1
                pid = item.get("player_id") or "?"
                names.append(str(pid))
    return count, names[:5]


def context_score(
    home_metrics: dict,
    away_metrics: dict,
    home_xg_for: float,
    home_xg_against: float,
    away_xg_for: float,
    away_xg_against: float,
    h2h: dict,
    home_absences: int = 0,
    away_absences: int = 0,
    market_key: str = "btts_yes",
) -> tuple[float, list[str]]:
    """Score 0-100 + lista de razones (positivas y negativas)."""
    score = 50.0
    reasons: list[str] = []
    now = datetime.now(timezone.utc)

    if market_key in ("btts_yes", "over_25"):
        hb = home_metrics.get("btts_rate", 0.5)
        ab = away_metrics.get("btts_rate", 0.5)
        if hb >= BTTS_RATE_GOOD:
            score += 8
            reasons.append(f"Home BTTS {hb:.0%} ✓")
        elif hb < 0.40:
            score -= 10
            reasons.append(f"Home BTTS {hb:.0%} bajo")
        if ab >= BTTS_RATE_GOOD:
            score += 8
            reasons.append(f"Away BTTS {ab:.0%} ✓")
        elif ab < 0.40:
            score -= 10
            reasons.append(f"Away BTTS {ab:.0%} bajo")

        if home_xg_against >= XGA_SOFT_MIN:
            score += 5
        else:
            score -= 6
            reasons.append(f"Home xGA {home_xg_against:.2f} bajo")
        if away_xg_against >= XGA_SOFT_MIN:
            score += 5
        else:
            score -= 6
            reasons.append(f"Away xGA {away_xg_against:.2f} bajo")

        hcs = home_metrics.get("clean_sheet_rate", 0.3)
        acs = away_metrics.get("clean_sheet_rate", 0.3)
        if hcs > CLEAN_SHEET_SOFT_MAX:
            score -= 7
            reasons.append(f"Home CS {hcs:.0%} alto")
        if acs > CLEAN_SHEET_SOFT_MAX:
            score -= 7
            reasons.append(f"Away CS {acs:.0%} alto")

    elif market_key in ("btts_no", "under_25"):
        hb = home_metrics.get("btts_rate", 0.5)
        ab = away_metrics.get("btts_rate", 0.5)
        if hb < 0.45:
            score += 8
        if ab < 0.45:
            score += 8
        if home_xg_against < 1.1:
            score += 5
        if away_xg_against < 1.1:
            score += 5

    hr = rest_days(home_metrics, now)
    ar = rest_days(away_metrics, now)
    if hr < REST_DAYS_MIN:
        score -= 12
        reasons.append(f"Home solo {hr:.0f}d descanso")
    elif hr >= REST_DAYS_IDEAL:
        score += 3
    if ar < REST_DAYS_MIN:
        score -= 12
        reasons.append(f"Away solo {ar:.0f}d descanso")
    elif ar >= REST_DAYS_IDEAL:
        score += 3

    if h2h:
        if market_key == "btts_yes" and h2h.get("btts_rate", 0) >= 0.55:
            score += 6
            reasons.append(f"H2H BTTS {h2h['btts_rate']:.0%}")
        elif market_key == "btts_yes" and h2h.get("btts_rate", 0) < 0.35:
            score -= 8
            reasons.append(f"H2H BTTS {h2h['btts_rate']:.0%} bajo")
        if market_key == "over_25" and h2h.get("over25_rate", 0) >= 0.55:
            score += 5

    if home_absences >= 2:
        score -= 5 * min(home_absences, 3)
        reasons.append(f"Home {home_absences} bajas")
    if away_absences >= 2:
        score -= 5 * min(away_absences, 3)
        reasons.append(f"Away {away_absences} bajas")

    if market_key in ("btts_yes", "over_25", "home_win", "away_win"):
        if home_metrics.get("goals_for_avg", 0) >= 1.5:
            score += 4
        if away_metrics.get("goals_for_avg", 0) >= 1.5:
            score += 4

    score = max(0.0, min(100.0, score))
    return score, reasons


def passes_hard_filters(
    home_metrics: dict,
    away_metrics: dict,
    context: float,
) -> tuple[bool, list[str]]:
    """Solo rechazos duros (datos insuficientes o score muy bajo)."""
    reasons = []
    if home_metrics.get("matches", 0) < 4:
        reasons.append("Home < 4 partidos recientes")
    if away_metrics.get("matches", 0) < 4:
        reasons.append("Away < 4 partidos recientes")
    if context < MIN_CONTEXT_SCORE:
        reasons.append(f"Context score {context:.0f} < {MIN_CONTEXT_SCORE}")
    return len(reasons) == 0, reasons
