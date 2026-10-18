"""
Orquestador en vivo: analiza partidos en curso con cuotas live.
Usa stats live cuando están disponibles y el mismo motor multi-mercado.
"""
from __future__ import annotations

import logging
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.config import COMPETITION_IDS, MAX_MATCHES, MAX_WORKERS, RECENT_MATCHES_N
from src.api_client import (
    matches, match_live_stats, match_odds_live,
    team_recent_matches, match_stats, team_id_from_match,
)
from src.analyzer import analyze
from src.telegram_bot import send_analysis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


def _process_live(m: dict) -> dict | None:
    mid = m.get("id", "?")
    home = (m.get("home_team") or {}).get("name", "?")
    away = (m.get("away_team") or {}).get("name", "?")
    home_id = team_id_from_match(m, "home")
    away_id = team_id_from_match(m, "away")

    try:
        st = match_live_stats(mid) or {}
        od = match_odds_live(mid)
        if not od or not od.get("bookmakers"):
            return None

        home_recent = team_recent_matches(home_id, min(8, RECENT_MATCHES_N))
        away_recent = team_recent_matches(away_id, min(8, RECENT_MATCHES_N))
        home_stats: dict[str, dict] = {}
        away_stats: dict[str, dict] = {}
        for rm in home_recent[:5]:
            rid = rm.get("id")
            if rid and rm.get("xg_available"):
                home_stats[rid] = match_stats(rid)
        for rm in away_recent[:5]:
            rid = rm.get("id")
            if rid and rm.get("xg_available"):
                away_stats[rid] = match_stats(rid)

        result = analyze(
            match=m,
            st=st,
            od=od,
            home_recent=home_recent,
            away_recent=away_recent,
            home_stats_cache=home_stats,
            away_stats_cache=away_stats,
        )
        if result and result.get("has_value"):
            best = result["best_pick"]
            log.info(
                "  ✓ LIVE %s vs %s → %s P=%.0f%% Edge=%+.1f%%",
                home, away, best["market_label"],
                best["p_model"] * 100, best["edge"] * 100,
            )
        return result
    except Exception as e:
        log.warning("  ✗ live %s: %s", mid, e)
        return None


def main():
    today = date.today().isoformat()
    log.info("═══ Value Finder LIVE %s ═══", today)

    live_matches: list[dict] = []
    if COMPETITION_IDS:
        for cid in COMPETITION_IDS:
            live_matches.extend(
                matches(date_from=today, date_to=today, status="live", competition_id=cid)
            )
    else:
        live_matches = matches(date_from=today, date_to=today, status="live")

    log.info("Partidos en vivo: %d", len(live_matches))
    eligible = [m for m in live_matches if m.get("live_odds_available")]
    log.info("Con cuotas live: %d", len(eligible))

    results: list[dict] = []
    total = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_process_live, m): m for m in eligible[:MAX_MATCHES]}
        for fut in as_completed(futures):
            try:
                r = fut.result(timeout=45)
                if r:
                    results.append(r)
            except Exception:
                pass
            total += 1

    n_value = sum(1 for r in results if r.get("has_value"))
    log.info("═══ Analizados live: %d | Con value: %d ═══", total, n_value)

    if n_value > 0:
        send_analysis(results, f"{today} LIVE", total)
    else:
        log.info("Sin oportunidades live por encima de umbral.")


if __name__ == "__main__":
    main()
