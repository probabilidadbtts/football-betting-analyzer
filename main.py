"""
Pre-match: solo ligas reconocidas + sin juveniles/U21/reservas.
Predicción con xG de últimos 5 home del local y 5 away del visitante.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from src.config import (
    COMPETITION_IDS, TOP_COMPETITION_IDS, MAX_MATCHES, MAX_WORKERS,
    SAVE_PICKS_JSON, PICKS_DIR, YOUTH_KEYWORDS,
)
from src.api_client import (
    matches, match_odds,
    team_home_matches, team_away_matches,
    team_injuries_suspensions, team_squad,
    team_id_from_match, team_name_from_match,
)
from src.analyzer import analyze_match
from src.telegram_bot import send_report

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def _is_youth_team(name: str) -> bool:
    if not name:
        return False
    lower = f" {name.lower()} "
    return any(kw in lower for kw in YOUTH_KEYWORDS)


def _get_competitions() -> list[str]:
    if COMPETITION_IDS:
        return COMPETITION_IDS
    return TOP_COMPETITION_IDS


def _process_single(m: dict) -> dict | None:
    mid = m.get("id")
    if not mid:
        return None

    home = team_name_from_match(m, "home")
    away = team_name_from_match(m, "away")

    # Descartar juveniles / U21 / reservas
    if _is_youth_team(home) or _is_youth_team(away):
        log.debug("Descartado (juvenil): %s vs %s", home, away)
        return None

    try:
        od = match_odds(mid)
        if not od or not od.get("bookmakers"):
            return None

        hid = team_id_from_match(m, "home")
        aid = team_id_from_match(m, "away")

        h_home = team_home_matches(hid, n=5)
        a_away = team_away_matches(aid, n=5)

        h_inj = team_injuries_suspensions(hid, current=True)
        a_inj = team_injuries_suspensions(aid, current=True)
        h_squad = team_squad(hid)
        a_squad = team_squad(aid)

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
        log.warning("Error %s: %s", mid, e)
        return None


def main():
    today = date.today().isoformat()
    log.info("Pre-Match (ligas reconocidas, sin juveniles) — %s", today)

    comps = _get_competitions()
    pool: list[dict] = []

    if comps:
        for cid in comps:
            pool.extend(
                matches(date_from=today, date_to=today, status="scheduled", competition_id=cid)
            )
        log.info("Competiciones filtradas: %d", len(comps))
    else:
        # Si no hay lista, analiza todas pero luego filtra juveniles
        pool = matches(date_from=today, date_to=today, status="scheduled")
        log.info("Sin filtro de competición (todas las ligas), se eliminarán juveniles")

    seen, unique = set(), []
    for m in pool:
        mid = m.get("id")
        if mid and mid not in seen:
            seen.add(mid)
            unique.append(m)

    eligible = [m for m in unique if m.get("odds_available")]
    log.info("Partidos con cuotas (antes de filtrar juveniles): %d", len(eligible))

    candidates = eligible[:MAX_MATCHES]
    results, value_matches = [], []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as exe:
        futs = {exe.submit(_process_single, m): m for m in candidates}
        for fut in as_completed(futs):
            res = fut.result()
            if res:
                results.append(res)
                if res.get("has_value"):
                    value_matches.append(res)
                    log.info(
                        "✓ %s vs %s | xG H:%s A:%s | picks:%d",
                        res.get("home"), res.get("away"),
                        res.get("home_xg_matches"), res.get("away_xg_matches"),
                        len(res.get("value_picks") or []),
                    )

    log.info("Analizados: %d | Con valor: %d", len(results), len(value_matches))

    if SAVE_PICKS_JSON:
        Path(PICKS_DIR).mkdir(parents=True, exist_ok=True)
        with open(f"{PICKS_DIR}/prematch_{today}.json", "w", encoding="utf-8") as f:
            json.dump({"title": f"PRE-MATCH {today}", "matches": results}, f, ensure_ascii=False, indent=2, default=str)

    send_report(value_matches, f"PRE-MATCH {today}", len(results))


if __name__ == "__main__":
    main()
