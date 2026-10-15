"""
Motor de análisis principal.
Combina Poisson + cuotas + filtros + Kelly.
"""
import logging
from datetime import datetime, timezone
from .config import (
    PROB_THRESHOLD_SINGLE, PROB_THRESHOLD_ACCA,
    VALUE_MARGIN,
)
from .poisson_model import p_btts, p_over_2_5, dixon_coles_correction
from .filters import (
    compute_team_metrics, compute_xg_metrics,
    h2h_btts_rate, apply_filters,
)
from .kelly import has_value, ev_percent, kelly_stake, breakeven_odds, classify_level

log = logging.getLogger(__name__)

FORM_BOOST = 0.05
ABSENCE_PENALTY = 0.05


def _f(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _d(v) -> dict:
    """Devuelve dict garantizado (protege contra None)."""
    return v if isinstance(v, dict) else {}


def _l(v) -> list:
    """Devuelve list garantizado (protege contra None)."""
    return v if isinstance(v, list) else []


def _extract_odds_value(odd) -> float | None:
    """Extrae valor numérico de un campo de odds (puede ser str, dict o float)."""
    if isinstance(odd, dict):
        return _f(odd.get("last_seen") or odd.get("current") or odd.get("live"))
    return _f(odd)


def _compute_form(recent_matches: list[dict], team_id: str) -> tuple[int, int, int]:
    """(wins, draws, losses) en últimos partidos."""
    wins = draws = losses = 0
    for m in _l(recent_matches):
        home_id = (_d(m.get("home_team"))).get("id")
        away_id = (_d(m.get("away_team"))).get("id")
        sh = _f((_d(m.get("home_team"))).get("score"))
        sa = _f((_d(m.get("away_team"))).get("score"))
        if sh is None or sa is None:
            continue
        if team_id == home_id:
            if sh > sa: wins += 1
            elif sh == sa: draws += 1
            else: losses += 1
        elif team_id == away_id:
            if sa > sh: wins += 1
            elif sa == sh: draws += 1
            else: losses += 1
    return wins, draws, losses


def _check_absences(lineups_data: dict, players_list: list[dict], side: str) -> list[str]:
    """Delanteros clave ausentes del XI."""
    if not lineups_data or not players_list:
        return []
    side_data = _d(lineups_data.get(side))
    xi = _l(side_data.get("starting_xi"))
    subs = _l(side_data.get("substitutes"))
    present_ids = {p.get("player_id") or p.get("id") for p in xi + subs}

    forward_positions = {"ST", "CF", "LW", "RW", "FW"}
    absent = []
    for p in players_list:
        pos = str(p.get("position", "")).upper()
        if any(fp in pos for fp in forward_positions):
            pid = p.get("id") or p.get("player_id")
            if pid and pid not in present_ids:
                absent.append(p.get("name", "?"))
    return absent


def analyze(match: dict,
            st: dict,
            od: dict,
            home_recent: list[dict],
            away_recent: list[dict],
            home_stats_cache: dict[str, dict],
            away_stats_cache: dict[str, dict],
            h2h_matches: list[dict] | None = None,
            lineups_data: dict | None = None,
            home_players: list[dict] | None = None,
            away_players: list[dict] | None = None,
            ) -> dict | None:
    """
    Analiza un partido completo. Devuelve dict con resultados o None.
    """
    # ═══ 0. EXTRAER NOMBRES (protegido) ═══
    home = (_d(match.get("home_team"))).get("name", "Home")
    away = (_d(match.get("away_team"))).get("name", "Away")
    home_id = (_d(match.get("home_team"))).get("id", "")
    away_id = (_d(match.get("away_team"))).get("id", "")

    # ═══ 1. xG DEL MATCH ═══
    st = _d(st)
    xg_h = _f(st.get("home", {}).get("xg")) or _f(
        _d(_d(st.get("overview")).get("expected_goals")).get("all", {}).get("home")
    ) if isinstance(st.get("overview"), dict) else None
    xg_a = _f(st.get("away", {}).get("xg")) or _f(
        _d(_d(st.get("overview")).get("expected_goals")).get("all", {}).get("away")
    ) if isinstance(st.get("overview"), dict) else None

    # ═══ 2. MÉTRICAS DE EQUIPOS ═══
    home_metrics = compute_team_metrics(home_recent, home_id)
    away_metrics = compute_team_metrics(away_recent, away_id)

    home_xg_for, home_xg_against = compute_xg_metrics(home_recent, home_id, home_stats_cache)
    away_xg_for, away_xg_against = compute_xg_metrics(away_recent, away_id, away_stats_cache)

    # ═══ 3. MODELO POISSON / DIXON-COLES ═══
    lambda_home = (home_xg_for + away_xg_against) / 2.0
    lambda_away = (away_xg_for + home_xg_against) / 2.0

    if xg_h is not None and xg_a is not None:
        lambda_home = (lambda_home + xg_h) / 2.0
        lambda_away = (lambda_away + xg_a) / 2.0

    p_poisson = p_btts(lambda_home, lambda_away)
    p_poisson_dc = dixon_coles_correction(p_poisson, lambda_home, lambda_away, rho=-0.1)

    # ═══ 4. CUOTAS DE MERCADO ═══
    od = _d(od)
    bookmakers = _l(od.get("bookmakers"))
    btts_odds: float | None = None
    btts_bookmaker: str = ""

    for bk in bookmakers:
        if not isinstance(bk, dict):
            continue
        markets = _d(bk.get("markets"))
        btts = _d(markets.get("btts"))
        btts_yes = btts.get("yes")
        val = _extract_odds_value(btts_yes)
        if val and val > 1.0:
            if bk.get("bookmaker") == "Pinnacle" or btts_odds is None:
                btts_odds = val
                btts_bookmaker = bk.get("bookmaker", "?")

    p_market = 1.0 / btts_odds if btts_odds and btts_odds > 1.0 else None

    # ═══ 5. AJUSTES: FORMA + AUSENCIAS ═══
    form_boost = 0.0
    h_w, _, _ = _compute_form(home_recent, home_id)
    a_w, _, _ = _compute_form(away_recent, away_id)
    if h_w >= 4 and home_xg_for >= 1.2:
        form_boost = FORM_BOOST
    elif a_w >= 4 and away_xg_for >= 1.2:
        form_boost = FORM_BOOST

    lineups_data = _d(lineups_data)
    home_absent = _check_absences(_d(lineups_data.get("home")), _l(home_players))
    away_absent = _check_absences(_d(lineups_data.get("away")), _l(away_players))
    home_penalty = ABSENCE_PENALTY if home_absent else 0.0
    away_penalty = ABSENCE_PENALTY if away_absent else 0.0

    # ═══ 6. FILTROS ═══
    current_date = datetime.now(timezone.utc)
    h2h_btts = h2h_btts_rate(h2h_matches) if h2h_matches else None

    filters_passed, filter_reasons = apply_filters(
        home_metrics=home_metrics,
        away_metrics=away_metrics,
        home_xg_for=home_xg_for,
        home_xg_against=home_xg_against,
        away_xg_for=away_xg_for,
        away_xg_against=away_xg_against,
        h2h_btts=h2h_btts,
        current_date=current_date,
    )

    # ═══ 7. PROBABILIDAD FINAL ═══
    if p_market:
        p_model = 0.5 * p_poisson_dc + 0.5 * p_market + form_boost - (home_penalty + away_penalty) / 2
    else:
        p_model = p_poisson_dc + form_boost - (home_penalty + away_penalty) / 2
    p_model = min(0.99, max(0.01, p_model))

    # ═══ 8. VALUE + KELLY + NIVEL ═══
    value_flag = has_value(p_model, btts_odds, VALUE_MARGIN) if btts_odds else False
    ev = ev_percent(p_model, btts_odds) if btts_odds else 0.0
    stake = kelly_stake(p_model, btts_odds) if btts_odds and value_flag else 0.0
    level = classify_level(p_model, ev, value_flag)

    # ═══ 9. RESULTADO ═══
    return {
        "home": home,
        "away": away,
        "home_id": home_id,
        "away_id": away_id,
        "p_poisson": p_poisson,
        "p_poisson_dc": p_poisson_dc,
        "p_market": p_market,
        "p_model": p_model,
        "lambda_home": lambda_home,
        "lambda_away": lambda_away,
        "btts_odds": btts_odds,
        "btts_bookmaker": btts_bookmaker,
        "value": value_flag,
        "ev": ev,
        "stake": stake,
        "level": level,
        "filters_passed": filters_passed,
        "filter_reasons": filter_reasons,
        "form_boost": form_boost,
        "home_penalty": home_penalty,
        "away_penalty": away_penalty,
        "home_absent": home_absent,
        "away_absent": away_absent,
        "home_btts_rate": home_metrics.get("btts_rate", 0),
        "away_btts_rate": away_metrics.get("btts_rate", 0),
        "home_xg_against": home_xg_against,
        "away_xg_against": away_xg_against,
        "h2h_btts": h2h_btts,
    }   
