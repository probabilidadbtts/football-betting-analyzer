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
from src.telegram_bot import send

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def _process_match(m: dict) -> list[str]:
    """Procesa UN partido: stats + odds + form + lineups + players → apuestas."""
    mid = m.get("id", "?")
    home = m.get("home_team", {}).get("name", "?")
    away = m.get("away_team", {}).get("name", "?")
    home_id = m.get("home_team", {}).get("id", "")
    away_id = m.get("away_team", {}).get("id", "")

    try:
        # Llamadas principales
        st = match_stats(mid) if m.get("xg_available") else {}
        od = match_odds(mid)

        # Llamadas secundarias (opcionales)
        form_data = None
        try:
            form_data = {
                "home": team_recent_matches(home_id, 5),
                "away": team_recent_matches(away_id, 5),
            }
        except Exception:
            pass

        lineups_data = {}
        home_players: list[dict] = []
        away_players: list[dict] = []
        try:
            lineups_data = match_lineups(mid)
            if lineups_data:
                home_players = team_players(home_id)
                away_players = team_players(away_id)
        except Exception:
            pass

        bets = analyze(
            match=m, st=st, od=od,
            form_data=form_data,
            lineups_data=lineups_data,
            home_players=home_players,
            away_players=away_players,
        )
        if bets:
            log.info("  ✓ %s vs %s → %d apuestas", home, away, len(bets))
        return bets

    except Exception as e:
        log.warning("  ✗ %s vs %s: %s", home, away, e)
        return []


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

    all_bets: list[str] = []
    total_analyzed = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(_process_match, m): m
            for m in eligible[:MAX_MATCHES]
        }
        for future in as_completed(futures):
            try:
                bets = future.result(timeout=30)
                all_bets.extend(bets)
            except Exception as e:
                m = futures[future]
                log.warning("  ✗ timeout: %s", e)
            total_analyzed += 1
            if total_analyzed % 10 == 0:
                log.info("  Progreso: %d/%d", total_analyzed, len(eligible[:MAX_MATCHES]))

    log.info("═══ Analizados: %d | Apuestas: %d ═══", total_analyzed, len(all_bets))

    if all_bets:
        header = (
            f"🏆 <b>MEJORES OPORTUNIDADES — {today}</b>\n"
            f"📊 {total_analyzed} partidos analizados\n\n"
        )
        body = "\n".join(all_bets[:30])
        msg = header + body
        if len(msg) > 4000:
            msg = header + body[:3900] + "\n…(truncado)"
        send(msg)
    else:
        send(f"📭 Sin oportunidades por encima del umbral hoy ({today}).")


if __name__ == "__main__":
    main()   
