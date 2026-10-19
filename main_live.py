"""
Orquestador LIVE: analiza partidos en juego de TODAS las ligas
y finaliza el workflow en cuanto encuentra TARGET_VALUE_MATCHES partidos con valor.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone, date
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED
from pathlib import Path

from src.config import (
    COMPETITION_IDS, MAX_MATCHES, MAX_WORKERS,
    RECENT_MATCHES_N, SAVE_PICKS_JSON, PICKS_DIR, TARGET_VALUE_MATCHES,
)
from src.api_client import (
    matches, match_live_stats, match_odds_live, match_stats,
    team_recent_matches, team_injuries_suspensions,
    team_id_from_match, team_name_from_match,
    extract_live_match_state,
)
from src.analyzer import analyze_match
from src.telegram_bot import send_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)


def _process_live_match(m: dict, idx: int, total: int) -> dict | None:
    mid = m.get("id")
    if not mid:
        return None

    home_name = team_name_from_match(m, "home")
    away_name = team_name_from_match(m, "away")
    tag = f"[{idx}/{total}] {home_name} vs {away_name}"

    try:
        st = match_live_stats(mid) or {}
        minute, h_goals, a_goals = extract_live_match_state(m, st)

        if minute < 8:
            log.info("%s -> Descartado: Minuto %d' (temprano)", tag, minute)
            return None
        if minute > 85:
            log.info("%s -> Descartado: Minuto %d' (tarde)", tag, minute)
            return None

        od = match_odds_live(mid)
        bookmakers = (od or {}).get("bookmakers") or []
        if not bookmakers:
            log.info("%s (Min %d') -> Cuotas suspendidas/vacías", tag, minute)
            return None

        hid = team_id_from_match(m, "home")
        aid = team_id_from_match(m, "away")

        h_rec = team_recent_matches(hid, min(8, RECENT_MATCHES_N))
        a_rec = team_recent_matches(aid, min(8, RECENT_MATCHES_N))

        h_cache: dict[str, dict] = {}
        a_cache: dict[str, dict] = {}
        for rm in h_rec[:3]:
            rid = rm.get("id")
            if rid and rm.get("xg_available"):
                h_cache[rid] = match_stats(rid)
        for rm in a_rec[:3]:
            rid = rm.get("id")
            if rid and rm.get("xg_available"):
                a_cache[rid] = match_stats(rid)

        h_inj = team_injuries_suspensions(hid, current=True)
        a_inj = team_injuries_suspensions(aid, current=True)

        result = analyze_match(
            match=m,
            odds_payload=od,
            home_recent=h_rec,
            away_recent=a_rec,
            home_stats_cache=h_cache,
            away_stats_cache=a_cache,
            home_injuries=h_inj,
            away_injuries=a_inj,
            is_live=True,
            minute=minute,
            current_home_goals=h_goals,
            current_away_goals=a_goals,
        )

        if result:
            picks_count = len(result.get("value_picks") or [])
            log.info("✓ %s (Min %d', %d-%d) -> ANALIZADO (%d picks)",
                     tag, minute, h_goals, a_goals, picks_count)
        return result

    except Exception as e:
        log.warning("%s -> Error: %s", tag, e)
        return None


def _save_picks(results: list[dict], title: str) -> None:
    if not SAVE_PICKS_JSON:
        return
    try:
        Path(PICKS_DIR).mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
        fname = f"{PICKS_DIR}/live_{ts}.json"
        payload = {
            "title": title,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "matches_with_value": len(results),
            "matches": results,
        }
        with open(fname, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
        log.info("Picks live guardados en %s", fname)
    except Exception as e:
        log.warning("No se pudieron guardar picks live: %s", e)


def main():
    today = datetime.now(timezone.utc).date().isoformat()
    log.info("=== LIVE SCAN (TODAS las ligas) — %s UTC ===", today)
    log.info("Objetivo: encontrar hasta %d partidos con valor y finalizar", TARGET_VALUE_MATCHES)

    # Todas las ligas si COMPETITION_IDS está vacío
    live_list: list[dict] = []
    if COMPETITION_IDS:
        for cid in COMPETITION_IDS:
            live_list.extend(
                matches(date_from=today, date_to=today, status="live", competition_id=cid)
            )
    else:
        live_list = matches(date_from=today, date_to=today, status="live")

    # Deduplicar
    seen = set()
    unique = []
    for m in live_list:
        mid = m.get("id")
        if mid and mid not in seen:
            seen.add(mid)
            unique.append(m)

    total_detected = len(unique)
    log.info("Partidos en juego detectados (todas las ligas): %d", total_detected)

    if not unique:
        log.info("No hay partidos en juego ahora.")
        send_report([], f"LIVE SCAN {today}", 0)
        return

    candidates = unique[:MAX_MATCHES]
    total_candidates = len(candidates)
    results: list[dict] = []          # solo los que tienen valor
    analyzed_count = 0

    log.info("Procesando hasta %d partidos (parada a %d con valor)...",
             total_candidates, TARGET_VALUE_MATCHES)

    with ThreadPoolExecutor(max_workers=min(4, MAX_WORKERS)) as pool:
        futures = {
            pool.submit(_process_live_match, m, i + 1, total_candidates): m
            for i, m in enumerate(candidates)
        }
        pending = set(futures.keys())

        while pending and len(results) < TARGET_VALUE_MATCHES:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for fut in done:
                analyzed_count += 1
                res = fut.result()
                if res and res.get("has_value"):
                    results.append(res)
                    log.info(
                        "✓ Valor LIVE (%d/%d): %s vs %s",
                        len(results), TARGET_VALUE_MATCHES,
                        res.get("home"), res.get("away"),
                    )

                if len(results) >= TARGET_VALUE_MATCHES:
                    for p in pending:
                        p.cancel()
                    log.info("🎯 Objetivo de %d partidos con valor alcanzado. Finalizando.", TARGET_VALUE_MATCHES)
                    break

    log.info(
        "=== Fin LIVE === Detectados: %d | Evaluados: %d | Con valor: %d",
        total_candidates, analyzed_count, len(results),
    )

    _save_picks(results, f"LIVE SCAN {today}")
    send_report(results, f"LIVE SCAN {today}", analyzed_count)


if __name__ == "__main__":
    main()
