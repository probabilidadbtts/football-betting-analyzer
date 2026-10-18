"""
Cliente HTTP robusto y tipado para TheStatsAPI con manejo de rate-limits y schemas reales.
"""
from __future__ import annotations

import logging
import time
from typing import Any
import requests

from .config import API_KEY, BASE_URL, PER_PAGE, TIMEOUT, MAX_RETRIES, RECENT_MATCHES_N

log = logging.getLogger(__name__)

_HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json",
    "User-Agent": "football-betting-analyzer/2.1",
}


def _get(path: str, params: dict | None = None, retries: int = MAX_RETRIES) -> dict:
    url = f"{BASE_URL}{path}"
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=_HEADERS, params=params or {}, timeout=TIMEOUT)
        except requests.exceptions.Timeout:
            log.warning("Timeout en %s (intento %d/%d)", path, attempt + 1, retries)
            if attempt < retries - 1:
                time.sleep(1.5 ** attempt)
                continue
            return {}
        except requests.exceptions.RequestException as e:
            log.warning("Error de red en %s: %s", path, e)
            return {}

        if r.status_code == 429:
            retry_after = int(r.headers.get("Retry-After", 2 ** attempt))
            log.warning("Rate limit 429 en %s. Esperando %ss", path, retry_after)
            time.sleep(retry_after)
            continue

        if r.status_code >= 500:
            time.sleep(1.5 ** attempt)
            continue

        if r.status_code in (404, 409):
            return {}

        try:
            r.raise_for_status()
            return r.json()
        except Exception as e:
            log.warning("Respuesta inválida en %s: %s", path, e)
            return {}

    return {}


def matches(
    date_from: str,
    date_to: str | None = None,
    status: str | None = None,
    competition_id: str | None = None,
    team_id: str | None = None,
    sort: str = "utc_date",
) -> list[dict]:
    date_to = date_to or date_from
    all_items: list[dict] = []
    page = 1

    while True:
        params: dict[str, Any] = {
            "date_from": date_from,
            "date_to": date_to,
            "per_page": PER_PAGE,
            "page": page,
            "sort": sort,
        }
        if status:
            params["status"] = status
        if competition_id:
            params["competition_id"] = competition_id
        if team_id:
            params["team_id"] = team_id

        resp = _get("/football/matches", params)
        data = resp.get("data")
        meta = resp.get("meta") or {}
        total_pages = meta.get("total_pages", 1)

        if not isinstance(data, list) or not data:
            break

        all_items.extend(data)
        if page >= total_pages:
            break
        page += 1

    return all_items


def team_recent_matches(team_id: str, n: int = RECENT_MATCHES_N) -> list[dict]:
    if not team_id:
        return []
    items = matches(
        date_from="2020-01-01",
        date_to="2099-12-31",
        status="finished",
        team_id=team_id,
        sort="-utc_date",
    )
    return items[:n]


def match_stats(match_id: str) -> dict:
    resp = _get(f"/football/matches/{match_id}/stats")
    return resp.get("data") or {}


def match_live_stats(match_id: str) -> dict:
    resp = _get(f"/football/matches/{match_id}/live-stats")
    return resp.get("data") or {}


def match_odds(match_id: str) -> dict:
    resp = _get(f"/football/matches/{match_id}/odds")
    return resp.get("data") or {}


def match_odds_live(match_id: str) -> dict:
    resp = _get(f"/football/matches/{match_id}/odds/live")
    return resp.get("data") or {}


def team_injuries_suspensions(team_id: str, current: bool = True) -> dict:
    if not team_id:
        return {}
    params = {"current": str(current).lower()}
    resp = _get(f"/football/teams/{team_id}/injuries-suspensions", params)
    return resp.get("data") or {}


def safe_score(match: dict, side: str) -> float | None:
    if not isinstance(match, dict):
        return None
    score = match.get("score")
    if isinstance(score, dict):
        v = score.get(side)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
        reg = score.get("regulation") or {}
        if isinstance(reg, dict) and reg.get(side) is not None:
            try:
                return float(reg[side])
            except (TypeError, ValueError):
                pass
    team = match.get(f"{side}_team") or {}
    if isinstance(team, dict) and team.get("score") is not None:
        try:
            return float(team["score"])
        except (TypeError, ValueError):
            pass
    return None


def team_id_from_match(match: dict, side: str) -> str:
    team = match.get(f"{side}_team") or {}
    return str(team.get("id") or "") if isinstance(team, dict) else ""


def team_name_from_match(match: dict, side: str) -> str:
    team = match.get(f"{side}_team") or {}
    return str(team.get("name") or side.title()) if isinstance(team, dict) else side.title()


def extract_live_match_state(match: dict, live_stats: dict) -> tuple[int, int, int]:
    """Obtiene minuto de juego y marcador actual en vivo."""
    minute = 0
    if "minute" in match:
        try:
            minute = int(match["minute"])
        except (ValueError, TypeError):
            minute = 45
    elif "minute" in live_stats:
        try:
            minute = int(live_stats["minute"])
        except (ValueError, TypeError):
            minute = 45

    sh = safe_score(match, "home")
    sa = safe_score(match, "away")
    h_goals = int(sh) if sh is not None else 0
    a_goals = int(sa) if sa is not None else 0

    return max(0, min(95, minute)), h_goals, a_goals
