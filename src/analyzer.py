"""
Motor de análisis: extrae mercados, calcula probabilidad implícita,
aplica boosts por forma y penalizaciones por ausencias.
Solo OVERS y BTTS SÍ — sin unders.
"""
import logging
from .config import PROB_THRESHOLD, FORM_BOOST, ABSENCE_PENALTY

log = logging.getLogger(__name__)


# ─── Utilidades ─────────────────────────────────────────────────────────────

def _f(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _prob(odds_val) -> float | None:
    o = _f(odds_val)
    return (1.0 / o) if o and o > 1.0 else None


# ─── Forma reciente ─────────────────────────────────────────────────────────

def _compute_form(matches_list: list[dict], team_id: str) -> tuple[int, int, int]:
    wins = draws = losses = 0
    for m in matches_list:
        home_id = m.get("home_team", {}).get("id")
        away_id = m.get("away_team", {}).get("id")
        score = m.get("score", {})
        score_h = _f(score.get("home"))
        score_a = _f(score.get("away"))
        if score_h is None or score_a is None:
            continue
        if team_id == home_id:
            if score_h > score_a: wins += 1
            elif score_h == score_a: draws += 1
            else: losses += 1
        elif team_id == away_id:
            if score_a > score_h: wins += 1
            elif score_a == score_h: draws += 1
            else: losses += 1
    return wins, draws, losses


# ─── Detección de ausencias ─────────────────────────────────────────────────

def _check_absences(lineups_data: dict, players_list: list[dict]) -> list[str]:
    """Devuelve nombres de delanteros clave ausentes del XI."""
    if not lineups_data or not players_list:
        return []

    xi = lineups_data.get("starting_xi", [])
    subs = lineups_data.get("substitutes", [])
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


# ─── Análisis principal ─────────────────────────────────────────────────────

def analyze(match: dict,
            st: dict,
            od: dict,
            form_data: dict | None = None,
            lineups_data: dict | None = None,
            home_players: list[dict] | None = None,
            away_players: list[dict] | None = None) -> list[str]:
    home = match.get("home_team", {}).get("name", "Home")
    away = match.get("away_team", {}).get("name", "Away")
    home_id = match.get("home_team", {}).get("id", "")
    away_id = match.get("away_team", {}).get("id", "")

    # ── xG ──
    overview = st.get("overview", {}) if st else {}
    xg_data = overview.get("expected_goals", {})
    xg_all = xg_data.get("all", {}) if isinstance(xg_data, dict) else {}
    xg_h = _f(xg_all.get("home", 0)) or 0
    xg_a = _f(xg_all.get("away", 0)) or 0
    total_xg = xg_h + xg_a

    # ── Forma ──
    form_boost = 0.0
    if form_data:
        h_w, _, _ = _compute_form(form_data.get("home", []), home_id)
        a_w, _, _ = _compute_form(form_data.get("away", []), away_id)
        if xg_h >= xg_a and h_w >= 4:
            form_boost = FORM_BOOST
        elif xg_a > xg_h and a_w >= 4:
            form_boost = FORM_BOOST

    # ── Ausencias ──
    home_absent = _check_absences(
        (lineups_data or {}).get("home", {}), home_players or [])
    away_absent = _check_absences(
        (lineups_data or {}).get("away", {}), away_players or [])
    home_penalty = ABSENCE_PENALTY if home_absent else 0.0
    away_penalty = ABSENCE_PENALTY if away_absent else 0.0

    # ── Evaluar mercados ──
    candidates: list[tuple[str, float]] = []
    bookmakers = od.get("bookmakers", []) if od else []

    for bk in bookmakers:
        markets = bk.get("markets", {})

        # BTTS SÍ
        btts = markets.get("btts") or {}
        btts_yes = btts.get("yes", {})
        btts_val = btts_yes.get("last_seen") or btts_yes.get("current") \
            if isinstance(btts_yes, dict) else btts_yes
        p = _prob(btts_val)
        if p:
            adj = p + form_boost - (home_penalty + away_penalty) / 2
            if adj >= PROB_THRESHOLD:
                tag = "⚠️" if (home_absent or away_absent) else "🎯"
                label = f"{tag} BTTS SÍ  {home} vs {away}  (P≈{p:.0%})"
                if home_absent:
                    label += f"  [⚡ {home_absent[0]}]"
                if away_absent:
                    label += f"  [⚡ {away_absent[0]}]"
                candidates.append((label, p))

        # Over 2.5 goles
        ou = markets.get("total_goals") or markets.get("over_under_25") or {}
        ou_over = ou.get("over", {})
        ou_val = ou_over.get("last_seen") or ou_over.get("current") \
            if isinstance(ou_over, dict) else ou_over
        p = _prob(ou_val)
        if p:
            adj = p + form_boost - (home_penalty + away_penalty) / 2
            if adj >= PROB_THRESHOLD:
                label = f"⚽ Over 2.5  {home} vs {away}  (P≈{p:.0%}, xG={total_xg:.2f})"
                candidates.append((label, p))

        # Over corners
        co = markets.get("corners_ou") or markets.get("corners") or {}
        co_over = co.get("over", {})
        co_val = co_over.get("last_seen") or co_over.get("current") \
            if isinstance(co_over, dict) else co_over
        line = co.get("line", "?")
        p = _prob(co_val)
        if p and p >= PROB_THRESHOLD:
            candidates.append((f"🥅 Over {line} corners  {home} vs {away}  (P≈{p:.0%})", p))

        # Asian Handicap (línea negativa = equipo que marca)
        ah = markets.get("asian_handicap") or {}
        ah_line = _f(ah.get("line"))
        p_home = _prob(ah.get("home"))
        p_away = _prob(ah.get("away"))
        if ah_line is not None and ah_line < 0:
            if p_home and (p_home + form_boost - home_penalty) >= PROB_THRESHOLD:
                candidates.append((f"🔥 {home} marca (AH {ah_line:+.1f})  (P≈{p_home:.0%})", p_home))
            if p_away and (p_away + form_boost - away_penalty) >= PROB_THRESHOLD:
                candidates.append((f"🔥 {away} marca (AH {ah_line:+.1f})  (P≈{p_away:.0%})", p_away))

    # ── Dedup: mejor prob por tipo ──
    best: dict[str, tuple[str, float]] = {}
    for label, p in candidates:
        key = label.split("  ")[0]
        if key not in best or p > best[key][1]:
            best[key] = (label, p)

    return [v[0] for v in sorted(best.values(), key=lambda x: -x[1])]   
