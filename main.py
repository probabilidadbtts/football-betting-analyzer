"""
Pre-match: solo partidos con historial xG.
Form: últimos 5 del local como local + últimos 5 del visitante como visitante.
Incluye impacto de bajas (market_value + posición).
Para al llegar a TARGET_VALUE_MATCHES.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from pathlib import Path

from src.config import (
    COMPETITION_IDS, MAX_MATCHES, MAX_WORKERS,
    SAVE_PICKS_JSON, PICKS_DIR, TARGET_VALUE_MATCHES,
)
from src.api_client import (
    matches, match_odds,
    team_home_matches, team_away_matches,
    team_injuries_suspensions, team_squad,
    team_id_from_match,
)
from src.analyzer import analyze_match
from src.telegram_bot import send_report

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def _process_single(m: dict) -> dict | None:
    mid = m.get("id")
    if not mid:
        return None

    # Solo partidos que tienen flag xG
    if not m.get("xg_available"):
        return None

    try:
        od = match_odds(mid)
        if not od or not od.get("bookmakers"):
            return None

        hid = team_id_from_match(m, "home")
        aid = team_id_from_match(m, "away")

        # Form específico de lado (5 partidos)
        h_home = team_home_matches(hid, n=5)
        a_away = team_away_matches(aid, n=5)

        # Lesiones + plantilla para impacto
        h_inj = team_injuries_suspensions(hid, current=True)
        a_inj = team_injuries_suspensions(aid, current=True)
        h_squad = team_squad(hid)
        a_squad = team_squad(aid)

        # H2H simple (desde los home del local)
        h2h = [
            rm for rm in h_home
            if team_id_from_match(rm, "home") == aid or team_id_from_match(rm, "away") == aid
        ]

        return analyze_match(
            match=m,
            odds_payload=od,
            home_home_matches=h_home,
            away_away_matches=a_away,
            home_injuries=h_inj,
            away_injuries=a_inj,
            home_squad=h_squad,
            away_squad=a_squad,
            h2h_matches=h2h,
            is_live=False,
        )
    except Exception as e:
        log.warning("Error procesando %s: %s", mid, e)
        return None


def _save_picks(results: list[dict], title: str) -> None:
    if not SAVE_PICKS_JSON:
        return
    try:
        Path(PICKS_DIR).mkdir(parents=True, exist_ok=True)
        fname = f"{PICKS_DIR}/prematch_{date.today().isoformat()}.json"
        with open(fname, "w", encoding="utf-8") as f:
            json.dump({
                "title": title,
                "generated_at": date.today().isoformat(),
                "matches_with_value": len(results),
                "matches": results,
            }, f, ensure_ascii=False, indent=2, default=str)
        log.info("Picks guardados en %s", fname)
    except Exception as e:
        log.warning("No se pudieron guardar picks: %s", e)


def main():
    today = date.today().isoformat()
    log.info("Pre-Match (solo xG + form home/away + bajas) — %s", today)
    log.info("Objetivo: %d partidos con valor", TARGET_VALUE_MATCHES)

    pool_matches: list[dict] = []
    if COMPETITION_IDS:
        for cid in COMPETITION_IDS:
            pool_matches.extend(
                matches(date_from=today, date_to=today, status="scheduled", competition_id=cid)
            )
    else:
        pool_matches = matches(date_from=today, date_to=today, status="scheduled")

    seen = set()
    unique = []
    for m in pool_matches:
        mid = m.get("id")
        if mid and mid not in seen:
            seen.add(mid)
            unique.append(m)

    # Solo con odds y con flag xG
    eligible = [m for m in unique if m.get("odds_available") and m.get("xg_available")]
    log.info("Partidos con cuotas + xG disponible: %d", len(eligible))

    if not eligible:
        send_report([], f"PRE-MATCH {today}", 0)
        return

    candidates = eligible[:MAX_MATCHES]
    value_matches: list[dict] = []
    analyzed = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_process_single, m): m for m in candidates}
        pending = set(futures.keys())

        while pending and len(value_matches) < TARGET_VALUE_MATCHES:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for fut in done:
                analyzed += 1
                res = fut.result()
                if res and res.get("has_value"):
                    value_matches.append(res)
                    log.info("✓ Valor (%d/%d): %s vs %s | xG H:%s A:%s | Impacto bajas H:%.0f A:%.0f",
                             len(value_matches), TARGET_VALUE_MATCHES,
                             res.get("home"), res.get("away"),
                             res.get("home_xg_matches"), res.get("away_xg_matches"),
                             res.get("home_injury_impact", 0), res.get("away_injury_impact", 0))

                if len(value_matches) >= TARGET_VALUE_MATCHES:
                    for p in pending:
                        p.cancel()
                    log.info("🎯 Objetivo alcanzado. Finalizando.")
                    break

    log.info("Resumen: analizados=%d | con valor=%d", analyzed, len(value_matches))
    _save_picks(value_matches, f"PRE-MATCH {today}")
    send_report(value_matches, f"PRE-MATCH {today}", analyzed)


if __name__ == "__main__":
    main()
