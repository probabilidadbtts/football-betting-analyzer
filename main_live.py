"""
Orquestador en vivo con logging en tiempo real para GitHub Actions.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.config import COMPETITION_IDS, MAX_MATCHES, MAX_WORKERS, RECENT_MATCHES_N
from src.api_client import (
    matches, match_live_stats, match_odds_live, match_stats,
    team_recent_matches, team_id_from_match, team_name_from_match,
    extract_live_match_state,
)
from src.analyzer import analyze_match
from src.telegram_bot import send_report

# Forzar flush inmediato en consola de GitHub Actions
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
        # 1. Verificar estado y minutos en juego
        st = match_live_stats(mid) or {}
        minute, h_goals, a_goals = extract_live_match_state(m, st)

        # Rango útil para operar en vivo (5' a 88')
        if minute < 5:
            log.info("%s -> Descartado: Minuto %d' (demasiado temprano)", tag, minute)
            return None
        if minute > 88:
            log.info("%s -> Descartado: Minuto %d' (partido por concluir)", tag, minute)
            return None

        # 2. Consultar cuotas en directo
        od = match_odds_live(mid)
        bookmakers = (od or {}).get("bookmakers") or []
        if not bookmakers:
            log.info("%s (Min %d') -> Descartado: Cuotas temporalmente suspendidas/vacias", tag, minute)
            return None

        # 3. Extraer contexto histórico (usando la caché en memoria)
        hid = team_id_from_match(m, "home")
        aid = team_id_from_match(m, "away")

        h_rec = team_recent_matches(hid, min(6, RECENT_MATCHES_N))
        a_rec = team_recent_matches(aid, min(6, RECENT_MATCHES_N))

        h_cache: dict[str, dict] = {}
        a_cache: dict[str, dict] = {}
        for rm in h_rec[:2]:
            rid = rm.get("id")
            if rid and rm.get("xg_available"):
                h_cache[rid] = match_stats(rid)
        for rm in a_rec[:2]:
            rid = rm.get("id")
            if rid and rm.get("xg_available"):
                a_cache[rid] = match_stats(rid)

        # 4. Análisis probabilístico con decaimiento de tiempo
        result = analyze_match(
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

        if result:
            picks_count = len(result.get("value_picks") or [])
            log.info("✓ %s (Min %d', %d-%d) -> ANALIZADO con éxito (%d picks con valor)", 
                     tag, minute, h_goals, a_goals, picks_count)
        return result

    except Exception as e:
        log.warning("%s -> Error durante el procesamiento: %s", tag, e)
        return None


def main():
    today = datetime.now(timezone.utc).date().isoformat()
    log.info("=== Iniciando escaneo LIVE (%s UTC) ===", today)

    live_list: list[dict] = []
    if COMPETITION_IDS:
        for cid in COMPETITION_IDS:
            live_list.extend(matches(date_from=today, date_to=today, status="live", competition_id=cid))
    else:
        live_list = matches(date_from=today, date_to=today, status="live")

    total_detected = len(live_list)
    log.info("Partidos en juego detectados en TheStatsAPI: %d", total_detected)

    if not live_list:
        log.info("No hay partidos en juego en este momento.")
        send_report([], f"LIVE SCAN {today}", 0)
        return

    candidates = live_list[:MAX_MATCHES]
    total_candidates = len(candidates)
    results: list[dict] = []
    analyzed_count = 0

    log.info("Procesando %d partidos con %d workers...", total_candidates, min(4, MAX_WORKERS))

    with ThreadPoolExecutor(max_workers=min(4, MAX_WORKERS)) as pool:
        futures = {
            pool.submit(_process_live_match, m, i + 1, total_candidates): m 
            for i, m in enumerate(candidates)
        }
        for fut in as_completed(futures):
            res = fut.result()
            if res:
                analyzed_count += 1
                if res.get("has_value"):
                    results.append(res)

    log.info("=== Fin del escaneo LIVE ===")
    log.info("Detectados: %d | Evaluados con cuotas activas: %d | Con valor real: %d", 
             total_candidates, analyzed_count, len(results))

    send_report(results, f"LIVE SCAN {today}", analyzed_count)


if __name__ == "__main__":
    main()
