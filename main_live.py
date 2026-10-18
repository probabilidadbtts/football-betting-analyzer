"""
Orquestador en vivo: analiza partidos en curso ajustando lambda por minuto y marcador.
"""
from __future__ import annotations

import logging
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.config import COMPETITION_IDS, MAX_MATCHES, MAX_WORKERS, RECENT_MATCHES_N
from src.api_client import (
    matches, match_live_stats, match_odds_live, match_stats,
    team_recent_matches, team_id_from_match, extract_live_match_state,
)
from src.analyzer import analyze_match
from src.telegram_bot import send_report

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def _process_live_match(m: dict) -> dict | None:
    mid = m.get("id")
    if not mid:
        return None

    try:
        od = match_odds_live(mid)
        if not od or not od.get("bookmakers"):
            return None

        st = match_live_stats(mid)
        minute, h_goals, a_goals = extract_live_match_state(m, st)

        # Evitar minutos finales extremos donde el mercado cierra o es ilíquido
        if minute > 85 or minute < 10:
            return None

        hid = team_id_from_match(m, "home")
        aid = team_id_from_match(m, "away")

        h_rec = team_recent_matches(hid, min(8, RECENT_MATCHES_N))
        a_rec = team_recent_matches(aid, min(8, RECENT_MATCHES_N))

        h_cache: dict[str, dict] = {}
        a_cache: dict[str, dict] = {}
        for rm in h_rec[:4]:
            rid = rm.get("id")
            if rid and rm.get("xg_available"):
                h_cache[rid] = match_stats(rid)
        for rm in a_rec[:4]:
            rid = rm.get("id")
            if rid and rm.get("xg_available"):
                a_cache[rid] = match_stats(rid)

        return analyze_match(
            match=m,
            odds_payload=od,
            home_recent=h_rec,
            away_recent=a_rec,
            home_stats_cache=h_cache,
            away_stats_cache=a_cache,
            is_live=True,
            minute=minute,
            current_home_goals=h_goals,
            current_away_goals=a_goals,
        )
    except Exception as e:
        log.warning("Error analizando partido live %s: %s", mid, e)
        return None


def main():
    today = date.today().isoformat()
    log.info("Iniciando escaneo LIVE: %s", today)

    live_list: list[dict] = []
    if COMPETITION_IDS:
        for cid in COMPETITION_IDS:
            live_list.extend(matches(date_from=today, date_to=today, status="live", competition_id=cid))
    else:
        live_list = matches(date_from=today, date_to=today, status="live")

    eligible = [m for m in live_list if m.get("live_odds_available")]
    log.info("Partidos en juego con cuotas live disponibles: %d", len(eligible))

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_process_live_match, m): m for m in eligible[:MAX_MATCHES]}
        for fut in as_completed(futures):
            res = fut.result()
            if res:
                results.append(res)

    send_report(results, f"LIVE SCAN {today}", len(results))


if __name__ == "__main__":
    main()
