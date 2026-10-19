"""
Pre-match: analiza todos los partidos del día con cuotas.
Predicción basada en xG de los últimos 5 como local (local) y 5 como visitante (visitante).
Sin tope de 20.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from src.config import COMPETITION_IDS, MAX_MATCHES, MAX_WORKERS, SAVE_PICKS_JSON, PICKS_DIR
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
    try:
        od = match_odds(mid)
        if not od or not od.get("bookmakers"):
            return None

        hid = team_id_from_match(m, "home")
        aid = team_id_from_match(m, "away")

        # Form específico + xG
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
    log.info("Pre-Match (predicción con xG home/away + bajas) — %s", today)

    pool = []
    if COMPETITION_IDS:
        for cid in COMPETITION_IDS:
            pool.extend(matches(date_from=today, date_to=today, status="scheduled", competition_id=cid))
    else:
        pool = matches(date_from=today, date_to=today, status="scheduled")

    seen, unique = set(), []
    for m in pool:
        mid = m.get("id")
        if mid and mid not in seen:
            seen.add(mid)
            unique.append(m)

    eligible = [m for m in unique if m.get("odds_available")]
    log.info("Partidos con cuotas: %d", len(eligible))
    if not eligible:
        send_report([], f"PRE-MATCH {today}", 0)
        return

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
                        "✓ %s vs %s | xG-matches H:%s A:%s | xG-for H:%.2f A:%.2f | bajas H:%.0f A:%.0f | picks:%d",
                        res.get("home"), res.get("away"),
                        res.get("home_xg_matches"), res.get("away_xg_matches"),
                        res.get("home_avg_xg_for") or 0, res.get("away_avg_xg_for") or 0,
                        res.get("home_injury_impact") or 0, res.get("away_injury_impact") or 0,
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
