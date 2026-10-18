"""
Orquestador pre-match: escaneo cuantitativo multihilo de la jornada completa.
"""
from __future__ import annotations

import logging
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.config import COMPETITION_IDS, MAX_MATCHES, MAX_WORKERS, RECENT_MATCHES_N
from src.api_client import (
    matches, match_stats, match_odds,
    team_recent_matches, team_injuries_suspensions,
    team_id_from_match,
)
from src.analyzer import analyze_match
from src.telegram_bot import send_report

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def _fetch_context(team_id: str) -> tuple[list[dict], dict[str, dict], dict]:
    if not team_id:
        return [], {}, {}
    recent = team_recent_matches(team_id, RECENT_MATCHES_N)
    stats_cache: dict[str, dict] = {}
    for m in recent[:6]:
        mid = m.get("id")
        if mid and m.get("xg_available"):
            stats_cache[mid] = match_stats(mid)
    injuries = team_injuries_suspensions(team_id, current=True)
    return recent, stats_cache, injuries


def _process_single(m: dict) -> dict | None:
    mid = m.get("id")
    if not mid:
        return None

    try:
        od = match_odds(mid)
        if not od or not od.get("bookmakers"):
            return None

        hid = team_id_from_match(m, "home")
        aid = team_id_from_match(m, "away")

        h_rec, h_cache, h_inj = _fetch_context(hid)
        a_rec, a_cache, a_inj = _fetch_context(aid)

        h2h = [
            rm for rm in h_rec
            if team_id_from_match(rm, "home") == aid or team_id_from_match(rm, "away") == aid
        ]

        return analyze_match(
            match=m,
            odds_payload=od,
            home_recent=h_rec,
            away_recent=a_rec,
            home_stats_cache=h_cache,
            away_stats_cache=a_cache,
            h2h_matches=h2h,
            home_injuries=h_inj,
            away_injuries=a_inj,
            is_live=False,
        )
    except Exception as e:
        log.warning("Error procesando partido %s: %s", mid, e)
        return None


def main():
    today = date.today().isoformat()
    log.info("Iniciando Value Finder Pre-Match para: %s", today)

    pool_matches: list[dict] = []
    if COMPETITION_IDS:
        for cid in COMPETITION_IDS:
            pool_matches.extend(matches(date_from=today, date_to=today, status="scheduled", competition_id=cid))
    else:
        pool_matches = matches(date_from=today, date_to=today, status="scheduled")

    eligible = [m for m in pool_matches if m.get("odds_available")]
    log.info("Total programados con cuotas: %d", len(eligible))

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_process_single, m): m for m in eligible[:MAX_MATCHES]}
        for fut in as_completed(futures):
            res = fut.result()
            if res:
                results.append(res)

    send_report(results, f"PRE-MATCH {today}", len(results))


if __name__ == "__main__":
    main()
