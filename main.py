"""
Orquestador pre-match: analiza todos los partidos del día
en busca de verdaderas oportunidades de value multi-mercado.
Paralelizado con ThreadPoolExecutor.
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
from src.analyzer import analyze
from src.telegram_bot import send_analysis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


def _fetch_team_context(team_id: str) -> tuple[list[dict], dict[str, dict], dict]:
    """Últimos N partidos + stats de cada uno + lesiones actuales."""
    if not team_id:
        return [], {}, {}
    recent = team_recent_matches(team_id, RECENT_MATCHES_N)
    stats_cache: dict[str, dict] = {}
    for m in recent:
        mid = m.get("id")
        if mid and m.get("xg_available"):
            stats_cache[mid] = match_stats(mid)
    injuries = team_injuries_suspensions(team_id, current=True)
    return recent, stats_cache, injuries


def _build_h2h(home_recent: list[dict], away_id: str) -> list[dict]:
    h2h = []
    for m in home_recent:
        hid = team_id_from_match(m, "home")
        aid = team_id_from_match(m, "away")
        if hid == away_id or aid == away_id:
            h2h.append(m)
    return h2h


def _process_match(m: dict) -> dict | None:
    mid = m.get("id", "?")
    home = (m.get("home_team") or {}).get("name", "?")
    away = (m.get("away_team") or {}).get("name", "?")
    home_id = team_id_from_match(m, "home")
    away_id = team_id_from_match(m, "away")

    try:
        st = match_stats(mid) if m.get("xg_available") else {}
        od = match_odds(mid)
        if not od or not od.get("bookmakers"):
            log.debug("  ⏭ %s vs %s — sin cuotas", home, away)
            return None

        home_recent, home_stats, home_inj = _fetch_team_context(home_id)
        away_recent, away_stats, away_inj = _fetch_team_context(away_id)
        h2h = _build_h2h(home_recent, away_id)

        result = analyze(
            match=m,
            st=st,
            od=od,
            home_recent=home_recent,
            away_recent=away_recent,
            home_stats_cache=home_stats,
            away_stats_cache=away_stats,
            h2h_matches=h2h,
            home_injuries=home_inj,
            away_injuries=away_inj,
        )

        if result and result.get("has_value"):
            best = result["best_pick"]
            log.info(
                "  ✓ %s vs %s → %s P=%.0f%% Edge=%+.1f%% L%d",
                home, away,
                best["market_label"],
                best["p_model"] * 100,
                best["edge"] * 100,
                best["level"],
            )
        elif result:
            log.debug("  · %s vs %s — sin value suficiente", home, away)
        return result

    except Exception as e:
        log.warning("  ✗ %s vs %s: %s", home, away, e)
        return None


def main():
    today = date.today().isoformat()
    log.info("═══ Value Finder pre-match %s ═══", today)

    day_matches: list[dict] = []
    if COMPETITION_IDS:
        for cid in COMPETITION_IDS:
            day_matches.extend(
                matches(date_from=today, date_to=today, status="scheduled", competition_id=cid)
            )
    else:
        day_matches = matches(date_from=today, date_to=today, status="scheduled")

    log.info("Partidos encontrados: %d", len(day_matches))
    eligible = [m for m in day_matches if m.get("odds_available")]
    log.info("Con cuotas disponibles: %d", len(eligible))

    results: list[dict] = []
    total = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(_process_match, m): m
            for m in eligible[:MAX_MATCHES]
        }
        for fut in as_completed(futures):
            try:
                r = fut.result(timeout=90)
                if r:
                    results.append(r)
            except Exception as e:
                log.warning("  timeout/error: %s", e)
            total += 1
            if total % 15 == 0:
                log.info("  Progreso: %d / %d", total, min(len(eligible), MAX_MATCHES))

    n_value = sum(1 for r in results if r.get("has_value"))
    log.info("═══ Analizados: %d | Con value: %d ═══", total, n_value)
    send_analysis(results, today, total)


if __name__ == "__main__":
    main()
