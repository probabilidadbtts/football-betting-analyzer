"""
Orquestador pre-match: analiza TODOS los partidos del día.
Una sola llamada a /football/matches?date_from=today&date_to=today
devuelve todas las competiciones. Sin IDs hardcoded.
"""
import logging
from datetime import date

from src.config import COMPETITION_IDS, MAX_MATCHES
from src.api_client import (
    matches, match_stats, match_odds,
    match_lineups, team_players, team_recent_matches,
)
from src.analyzer import analyze
from src.telegram_bot import send

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def main():
    today = date.today().isoformat()
    log.info("═══ Análisis pre-match %s ═══", today)

    # ── Obtener TODOS los partidos de hoy (todas las ligas) ──
    # Si COMPETITION_IDS está vacío → todas las competiciones
    comp_filter = COMPETITION_IDS[0] if COMPETITION_IDS else None
    day_matches = matches(
        date_from=today,
        date_to=today,
        status="scheduled",       # solo partidos por jugar
        competition_id=comp_filter,  # None = todas
    )
    log.info("Partidos encontrados: %d", len(day_matches))

    # Filtrar: solo los que tienen cuotas disponibles
    eligible = [m for m in day_matches if m.get("odds_available")]
    log.info("Con cuotas disponibles: %d", len(eligible))

    all_bets: list[str] = []
    total_analyzed = 0

    for m in eligible[:MAX_MATCHES]:
        mid = m.get("id")
        if not mid:
            continue

        home_id = m.get("home_team", {}).get("id", "")
        away_id = m.get("away_team", {}).get("id", "")

        try:
            # Estadísticas + xG (solo si está disponible)
            st = match_stats(mid) if m.get("xg_available") else {}

            # Cuotas pre-match
            od = match_odds(mid)

            # Forma (últimos 5 de cada equipo)
            form_data = {
                "home": team_recent_matches(home_id, 5),
                "away": team_recent_matches(away_id, 5),
            }

            # Lineups (si ya están confirmadas)
            lineups_data = {}
            try:
                lineups_data = match_lineups(mid)
            except Exception:
                pass

            # Plantillas (para detectar ausencias)
            home_players: list[dict] = []
            away_players: list[dict] = []
            try:
                home_players = team_players(home_id)
                away_players = team_players(away_id)
            except Exception:
                pass

            # Analizar
            bets = analyze(
                match=m,
                st=st,
                od=od,
                form_data=form_data,
                lineups_data=lineups_data,
                home_players=home_players,
                away_players=away_players,
            )
            all_bets.extend(bets)
            total_analyzed += 1

        except Exception as e:
            log.warning("  ⚠ %s (%s vs %s): %s",
                        mid,
                        m.get("home_team", {}).get("name", "?"),
                        m.get("away_team", {}).get("name", "?"),
                        e)

    log.info("Analizados: %d | Apuestas: %d", total_analyzed, len(all_bets))

    # ── Enviar a Telegram ──
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
