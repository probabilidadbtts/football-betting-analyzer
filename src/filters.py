"""
Filtros de validación estadística y contextual.
"""
import logging
from datetime import datetime
from .config import (
    BTTS_RATE_MIN, XGA_MIN, CLEAN_SHEET_MAX,
    CLEAN_SHEET_AWAY_MAX, REST_DAYS_MIN,
)

log = logging.getLogger(__name__)


def _f(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def compute_team_metrics(recent_matches: list[dict], team_id: str) -> dict:
    """
    Calcula métricas de un equipo a partir de sus últimos N partidos.
    Devuelve: {btts_rate, xg_for_avg, xg_against_avg, clean_sheet_rate, last_match_date}
    """
    if not recent_matches:
        return {}

    total = 0
    btts_count = 0
    xg_for_sum = 0.0
    xg_against_sum = 0.0
    clean_sheets = 0
    last_date = None

    for m in recent_matches:
        home_id = m.get("home_team", {}).get("id")
        away_id = m.get("away_team", {}).get("id")
        score_h = _f(m.get("home_team", {}).get("score"))
        score_a = _f(m.get("away_team", {}).get("score"))

        if score_h is None or score_a is None:
            continue

        # ¿Es este equipo?
        is_home = (home_id == team_id)
        my_goals = score_h if is_home else score_a
        opp_goals = score_a if is_home else score_h

        total += 1

        # BTTS
        if my_goals > 0 and opp_goals > 0:
            btts_count += 1

        # Clean sheet
        if opp_goals == 0:
            clean_sheets += 1

        # Fecha
        utc_date = m.get("utc_date") or m.get("date")
        if utc_date:
            try:
                d = datetime.fromisoformat(utc_date.replace("Z", "+00:00"))
                if last_date is None or d > last_date:
                    last_date = d
            except (ValueError, AttributeError):
                pass

    if total == 0:
        return {}

    return {
        "matches": total,
        "btts_rate": btts_count / total,
        "clean_sheet_rate": clean_sheets / total,
        "last_match_date": last_date,
    }


def compute_xg_metrics(recent_matches: list[dict], team_id: str,
                       stats_cache: dict[str, dict]) -> tuple[float, float]:
    """
    Calcula xG for y xG against promedio.
    stats_cache: {match_id: stats_data} para evitar re-llamadas.
    Devuelve: (xg_for_avg, xg_against_avg)
    """
    xg_for_list = []
    xg_against_list = []

    for m in recent_matches:
        mid = m.get("id")
        if not mid or mid not in stats_cache:
            continue
        st = stats_cache[mid]
        if not st:
            continue

        home_id = m.get("home_team", {}).get("id")
        is_home = (home_id == team_id)

        # xG del equipo
        if is_home:
            my_xg = _f(st.get("home", {}).get("xg")) or _f(
                st.get("overview", {}).get("expected_goals", {}).get("all", {}).get("home"))
            opp_xg = _f(st.get("away", {}).get("xg")) or _f(
                st.get("overview", {}).get("expected_goals", {}).get("all", {}).get("away"))
        else:
            my_xg = _f(st.get("away", {}).get("xg")) or _f(
                st.get("overview", {}).get("expected_goals", {}).get("all", {}).get("away"))
            opp_xg = _f(st.get("home", {}).get("xg")) or _f(
                st.get("overview", {}).get("expected_goals", {}).get("all", {}).get("home"))

        if my_xg is not None:
            xg_for_list.append(my_xg)
        if opp_xg is not None:
            xg_against_list.append(opp_xg)

    xg_for_avg = sum(xg_for_list) / len(xg_for_list) if xg_for_list else 1.0
    xg_against_avg = sum(xg_against_list) / len(xg_against_list) if xg_against_list else 1.0
    return xg_for_avg, xg_against_avg


def rest_days(metrics: dict, current_date: datetime) -> float:
    """Días de descanso desde el último partido."""
    last = metrics.get("last_match_date")
    if not last:
        return 99.0  # Desconocido → no penalizar
    return (current_date - last).days


def h2h_btts_rate(h2h_matches: list[dict]) -> float | None:
    """Tasa de BTTS en H2H reciente (últimos 5)."""
    if not h2h_matches:
        return None
    btts = 0
    total = 0
    for m in h2h_matches[:5]:
        sh = _f(m.get("home_team", {}).get("score"))
        sa = _f(m.get("away_team", {}).get("score"))
        if sh is None or sa is None:
            continue
        total += 1
        if sh > 0 and sa > 0:
            btts += 1
    return btts / total if total > 0 else None


def apply_filters(home_metrics: dict, away_metrics: dict,
                  home_xg_for: float, home_xg_against: float,
                  away_xg_for: float, away_xg_against: float,
                  h2h_btts: float | None,
                  current_date: datetime) -> tuple[bool, list[str]]:
    """
    Aplica todos los filtros. Devuelve (aprobado, razones_rechazo).
    """
    reasons: list[str] = []

    # 1. BTTS rate mínimo
    h_btts = home_metrics.get("btts_rate", 0)
    a_btts = away_metrics.get("btts_rate", 0)
    if h_btts < BTTS_RATE_MIN:
        reasons.append(f"Home BTTS rate {h_btts:.0%} < {BTTS_RATE_MIN:.0%}")
    if a_btts < BTTS_RATE_MIN:
        reasons.append(f"Away BTTS rate {a_btts:.0%} < {BTTS_RATE_MIN:.0%}")

    # 2. xGA mínimo (defensa porosa)
    if home_xg_against < XGA_MIN:
        reasons.append(f"Home xGA {home_xg_against:.2f} < {XGA_MIN}")
    if away_xg_against < XGA_MIN:
        reasons.append(f"Away xGA {away_xg_against:.2f} < {XGA_MIN}")

    # 3. Clean sheet rate máximo
    h_cs = home_metrics.get("clean_sheet_rate", 0)
    a_cs = away_metrics.get("clean_sheet_rate", 0)
    if h_cs > CLEAN_SHEET_AWAY_MAX:
        reasons.append(f"Home CS rate {h_cs:.0%} > {CLEAN_SHEET_AWAY_MAX:.0%}")
    if a_cs > CLEAN_SHEET_AWAY_MAX:
        reasons.append(f"Away CS rate {a_cs:.0%} > {CLEAN_SHEET_AWAY_MAX:.0%}")

    # 4. Descanso mínimo
    h_rest = rest_days(home_metrics, current_date)
    a_rest = rest_days(away_metrics, current_date)
    if h_rest < REST_DAYS_MIN:
        reasons.append(f"Home descanso {h_rest}d < {REST_DAYS_MIN}d")
    if a_rest < REST_DAYS_MIN:
        reasons.append(f"Away descanso {a_rest}d < {REST_DAYS_MIN}d")

    # 5. H2H BTTS (si hay datos)
    if h2h_btts is not None and h2h_btts < 0.40:
        reasons.append(f"H2H BTTS rate {h2h_btts:.0%} < 40%")

    approved = len(reasons) == 0
    return approved, reasons   
