"""
Orquestador pre-match: analiza TODOS los partidos del día (cualquier liga)
y finaliza el workflow en cuanto encuentra TARGET_VALUE_MATCHES partidos con valor.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED
from pathlib import Path

from src.config import (
    COMPETITION_IDS, MAX_MATCHES, MAX_WORKERS,
    RECENT_MATCHES_N, SAVE_PICKS_JSON, PICKS_DIR, TARGET_VALUE_MATCHES,
)
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
    for m in recent[:5]:
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


def _save_picks(results: list[dict], title: str) -> None:
    if not SAVE_PICKS_JSON:
        return
    try:
        Path(PICKS_DIR).mkdir(parents=True, exist_ok=True)
        fname = f"{PICKS_DIR}/prematch_{date.today().isoformat()}.json"
        payload = {
            "title": title,
            "generated_at": date.today().isoformat(),
            "matches_with_value": len([r for r in results if r.get("has_value")]),
            "matches": results,
        }
        with open(fname, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
        log.info("Picks guardados en %s", fname)
    except Exception as e:
        log.warning("No se pudieron guardar picks: %s", e)


def main():
    today = date.today().isoformat()
    log.info("Iniciando Value Finder Pre-Match (TODAS las ligas) — %s", today)
    log.info("Objetivo: encontrar hasta %d partidos con valor y finalizar", TARGET_VALUE_MATCHES)

    # --- Obtener partidos del día (todas las ligas si COMPETITION_IDS vacío) ---
    pool_matches: list[dict] = []
    if COMPETITION_IDS:
        for cid in COMPETITION_IDS:
            pool_matches.extend(
                matches(date_from=today, date_to=today, status="scheduled", competition_id=cid)
            )
    else:
        # Sin filtro de competición → todas las ligas
        pool_matches = matches(date_from=today, date_to=today, status="scheduled")

    # Deduplicar
    seen = set()
    unique = []
    for m in pool_matches:
        mid = m.get("id")
        if mid and mid not in seen:
            seen.add(mid)
            unique.append(m)

    eligible = [m for m in unique if m.get("odds_available")]
    log.info("Partidos programados con cuotas hoy: %d (todas las ligas)", len(eligible))

    if not eligible:
        log.info("No hay partidos con cuotas disponibles.")
        send_report([], f"PRE-MATCH {today}", 0)
        return

    # Limitar el pool máximo a analizar
    candidates = eligible[:MAX_MATCHES]
    log.info("Se intentarán analizar hasta %d partidos (parada anticipada a %d con valor)",
             len(candidates), TARGET_VALUE_MATCHES)

    results: list[dict] = []
    value_matches: list[dict] = []
    analyzed = 0

    # Procesamiento con parada anticipada
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_process_single, m): m for m in candidates}
        pending = set(futures.keys())

        while pending and len(value_matches) < TARGET_VALUE_MATCHES:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for fut in done:
                analyzed += 1
                res = fut.result()
                if res:
                    results.append(res)
                    if res.get("has_value"):
                        value_matches.append(res)
                        log.info(
                            "✓ Valor encontrado (%d/%d): %s vs %s — %d picks",
                            len(value_matches), TARGET_VALUE_MATCHES,
                            res.get("home"), res.get("away"),
                            len(res.get("value_picks") or []),
                        )

                if len(value_matches) >= TARGET_VALUE_MATCHES:
                    # Cancelar el resto de futuros pendientes
                    for p in pending:
                        p.cancel()
                    log.info("🎯 Objetivo de %d partidos con valor alcanzado. Finalizando workflow.", TARGET_VALUE_MATCHES)
                    break

    log.info(
        "Resumen PRE-MATCH: analizados=%d | con valor=%d | objetivo=%d",
        analyzed, len(value_matches), TARGET_VALUE_MATCHES,
    )

    # Enviar solo los que tienen valor
    _save_picks(value_matches, f"PRE-MATCH {today}")
    send_report(value_matches, f"PRE-MATCH {today}", analyzed)


if __name__ == "__main__":
    main()
