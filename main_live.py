"""
Orquestador en vivo: analiza partidos EN CURSO. Paralelizado.
"""
import logging
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.config import COMPETITION_IDS, MAX_MATCHES, MAX_WORKERS
from src.api_client import matches, match_stats, match_odds_live
from src.analyzer import analyze
from src.telegram_bot import send_analysis

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def _process_live(m: dict) -> dict | None:
    mid = m.get("id", "?")
    home = m.get("home_team", {}).get("name", "?")
    away = m.get("away_team", {}).get("name", "?")
    try:
        st = match_stats(mid) if m.get("xg_available") else {}
        od = match_odds_live(mid)
        if not od or not od.get("bookmakers"):
            return None
        result = analyze(
            match=m, st=st, od=od,
            home_recent=[], away_recent=[],
            home_stats_cache={}, away_stats_cache={},
        )
        if result:
            log.info("  ✓ %s vs %s → P=%.0f%% L%d",
                     home, away, result["p_model"] * 100, result["level"])
        return result
    except Exception as e:
        log.warning("  ✗ %s: %s", mid, e)
        return None


def main():
    today = date.today().isoformat()
    log.info("═══ Análisis en vivo %s ═══", today)

    comp_filter = COMPETITION_IDS[0] if COMPETITION_IDS else None
    live_matches = matches(
        date_from=today, date_to=today,
        status="live",
        competition_id=comp_filter,
    )
    log.info("Partidos en vivo: %d", len(live_matches))

    eligible = [m for m in live_matches if m.get("live_odds_available")]
    log.info("Con cuotas live: %d", len(eligible))

    results: list[dict] = []
    total = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_process_live, m): m for m in eligible[:MAX_MATCHES]}
        for future in as_completed(futures):
            try:
                r = future.result(timeout=30)
                if r:
                    results.append(r)
            except Exception:
                pass
            total += 1

    log.info("═══ Analizados: %d | Con datos: %d ═══", total, len(results))

    if results:
        send_analysis(results, today, total)
    else:
        log.info("Sin oportunidades en vivo. No se envía mensaje.")


if __name__ == "__main__":
    main()   
