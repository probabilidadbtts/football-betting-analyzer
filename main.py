"""
Orquestador pre-match: analiza TODOS los partidos del día.
Paralelizado con ThreadPoolExecutor.
"""
import logging
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.config import COMPETITION_IDS, MAX_MATCHES, MAX_WORKERS
from src.api_client import (
    matches, match_stats, match_odds,
    match_lineups, team_players, team_recent_matches,
)
from src.analyzer import analyze
from src.telegram_bot import send_analysis

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def _d(v) -> dict:
    return v if isinstance(v, dict) else {}


def _fetch_team_context(team_id: str) -> tuple[list[dict], dict[str, dict]]:
    """Obtiene últimos 10 partidos + stats de cada uno para un equipo."""
    if not team_id:
        return [], {}
    recent = team_recent_matches(team_id, 10)
    stats_cache: dict[str, dict] = {}
    for m in recent:
        mid = m.get("id")
        if mid:
            stats_cache[mid] = match_stats(mid)
    return recent, stats_cache


def _process_match(m: dict) -> dict | None:
    """Procesa UN partido completo."""
    mid = m.get("id", "?")
    home = (_d(m.get("home_team"))).get("name", "?")
    away = (_d(m.get("away_team"))).get("name", "?")
    home_id = (_d(m.get("home_team"))).get("id", "")
    away_id = (_d(m.get("away_team"))).get("id", "")

    try:
        # ── Llamadas principales ──
        st = match_stats(mid) if m.get("xg_available") else {}
        od = match_odds(mid)

        if not od or not od.get("bookmakers"):
            log.debug("  ⏭ %s vs %s: sin cuotas", home, away)
            return None

        # ── Contexto de equipos ──
        home_recent, home_stats_cache = _fetch_team_context(home_id)
        away_recent, away_stats_cache = _fetch_team_context(away_id)

        # ── H2H ──
        h2h = []
        for m2 in home_recent:
            h_id = (_d(m2.get("home_team"))).get("id")
            a_id = (_d(m2.get("away_team"))).get("id")
            if h_id == away_id or a_id == away_id:
                h2h.append(m2)

        # ── Lineups (opcionales) ──
        lineups_data = {}
        home_players: list[dict] = []
        away_players: list[dict] = []
        try:
            lineups_data = match_lineups(mid)
            if lineups_data and isinstance(lineups_data, dict) and lineups_data:
                home_players = team_players(home_id)
                away_players = team_players(away_id)
        except Exception:
            pass

        # ── Analizar ──
        result = analyze(
            match=m, st=st, od=od,
            home_recent=home_recent,
            away_recent=away_recent,
            home_stats_cache=home_stats_cache,
            away_stats_cache=away_stats_cache,
            h2h_matches=h2h,
            lineups_data=lineups_data,
            home_players=home_players,
            away_players=away_players,
        )

        if result:
            status = "✓" if result["filters_passed"] else "⛔"
            log.info("  %s %s vs %s → P=%.0f%% L%d",
                     status, home, away,
                     result["p_model"] * 100, result["level"])
        return result

    except Exception as e:
        log.warning("  ✗ %s vs %s: %s", home, away, e)
        return None


def main():
    today = date.today().isoformat()
    log.info("═══ Análisis pre-match %s ═══", today)

    comp_filter = COMPETITION_IDS[0] if COMPETITION_IDS else None
    day_matches = matches(
        date_from=today, date_to=today,
        status="scheduled",
        competition_id=comp_filter,
    )
    log.info("Partidos encontrados: %d", len(day_matches))

    eligible = [m for m in day_matches if m.get("odds_available")]
    log.info("Con cuotas disponibles: %d", len(eligible))

    results: list[dict] = []
    total_analyzed = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_process_match, m): m for m in eligible[:MAX_MATCHES]}
        for future in as_completed(futures):
            try:
                result = future.result(timeout=60)
                if result:
                    results.append(result)
            except Exception as e:
                log.warning("  ✗ timeout/error: %s", e)
            total_analyzed += 1
            if total_analyzed % 10 == 0:
                log.info("  Progreso: %d/%d", total_analyzed, min(len(eligible), MAX_MATCHES))

    log.info("═══ Analizados: %d | Con datos: %d ═══", total_analyzed, len(results))
    send_analysis(results, today, total_analyzed)


if __name__ == "__main__":
    main()   
