"""
Cliente HTTP robusto para TheStatsAPI.
Respeta rate-limits, maneja errores de forma segura y expone
todos los endpoints útiles para value betting.
"""
from __future__ import annotations

import time
import logging
from typing import Any
import requests

from .config import API_KEY, BASE_URL, PER_PAGE, TIMEOUT, MAX_RETRIES, RECENT_MATCHES_N

log = logging.getLogger(__name__)

_HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json",
    "User-Agent": "football-betting-analyzer/2.0",
}


def _get(path: str, params: dict | None = None, retries: int = MAX_RETRIES) -> dict:
    """GET con backoff exponencial ante 429/5xx. Nunca lanza excepciones no controladas."""
    url = f"{BASE_URL}{path}"
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=_HEADERS, params=params or {}, timeout=TIMEOUT)
        except requests.exceptions.Timeout:
            log.warning("TIMEOUT %s (attempt %d/%d)", path, attempt + 1, retries)
            if attempt < retries - 1:
                time.sleep(1.5 ** attempt)
                continue
            return {}
        except requests.exceptions.RequestException as e:
            log.warning("REQUEST ERROR %s → %s", path, e)
            return {}

        if r.status_code == 429:
            retry_after = int(r.headers.get("Retry-After", 2 ** attempt))
            log.warning("429 RATE_LIMIT %s → wait %ss", path, retry_after)
            time.sleep(retry_after)
            continue

        if r.status_code >= 500:
            log.warning("5xx %s status=%s", path, r.status_code)
            time.sleep(1.5 ** attempt)
            continue

        if r.status_code == 404:
            return {}

        if r.status_code == 409:
            log.debug("409 Conflict %s", path)
            return {}

        try:
            r.raise_for_status()
        except requests.exceptions.HTTPError as e:
            log.warning("HTTP %s → %s", path, e)
            return {}

        ct = r.headers.get("Content-Type", "")
        if "application/json" not in ct.lower():
            log.warning("Non-JSON %s content-type=%s", path, ct)
            return {}

        try:
            return r.json()
        except ValueError:
            log.warning("Invalid JSON %s", path)
            return {}

    return {}


# ─── Partidos ───────────────────────────────────────────────────────

def matches(
    date_from: str,
    date_to: str | None = None,
    status: str | None = None,
    competition_id: str | None = None,
    team_id: str | None = None,
    sort: str = "utc_date",
) -> list[dict]:
    """Lista partidos con paginación automática."""
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
        data = resp.get("data") or []
        meta = resp.get("meta") or {}
        total_pages = meta.get("total_pages", 1)

        if not isinstance(data, list):
            break

        all_items.extend(data)
        if page >= total_pages or not data:
            break
        page += 1

    return all_items


def team_recent_matches(team_id: str, n: int = RECENT_MATCHES_N) -> list[dict]:
    """Últimos N partidos terminados, del más reciente al más antiguo."""
    if not team_id:
        return []
    items = matches(
        date_from="2018-01-01",
        date_to="2099-12-31",
        status="finished",
        team_id=team_id,
        sort="-utc_date",
    )
    return items[:n]


def match_detail(match_id: str) -> dict:
    resp = _get(f"/football/matches/{match_id}")
    return resp.get("data") or {}


# ─── Stats & xG ─────────────────────────────────────────────────────

def match_stats(match_id: str) -> dict:
    """Stats post-partido (incluye xG). No usar en partidos live."""
    resp = _get(f"/football/matches/{match_id}/stats")
    return resp.get("data") or {}


def match_live_stats(match_id: str) -> dict:
    resp = _get(f"/football/matches/{match_id}/live-stats")
    return resp.get("data") or {}


def team_season_stats(team_id: str, season_id: str) -> dict:
    if not team_id or not season_id:
        return {}
    resp = _get(f"/football/teams/{team_id}/stats", {"season_id": season_id})
    return resp.get("data") or {}


# ─── Cuotas ─────────────────────────────────────────────────────────

def match_odds(match_id: str, bookmakers: str | None = None) -> dict:
    params = {}
    if bookmakers:
        params["bookmaker"] = bookmakers
    resp = _get(f"/football/matches/{match_id}/odds", params)
    return resp.get("data") or {}


def match_odds_live(match_id: str) -> dict:
    resp = _get(f"/football/matches/{match_id}/odds/live")
    return resp.get("data") or {}


# ─── Lineups, jugadores, lesiones ───────────────────────────────────

def match_lineups(match_id: str) -> dict:
    resp = _get(f"/football/matches/{match_id}/lineups")
    return resp.get("data") or {}


def team_players(team_id: str) -> list[dict]:
    resp = _get(f"/football/teams/{team_id}/players")
    data = resp.get("data")
    return data if isinstance(data, list) else []


def team_injuries_suspensions(team_id: str, current: bool = True) -> dict:
    params = {"current": str(current).lower()}
    resp = _get(f"/football/teams/{team_id}/injuries-suspensions", params)
    return resp.get("data") or {}


# ─── Helpers de extracción segura ───────────────────────────────────

def safe_score(match: dict, side: str) -> float | None:
    """Extrae goles de forma robusta (score.home o home_team.score)."""
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
    return (team.get("id") or "") if isinstance(team, dict) else ""


def team_name_from_match(match: dict, side: str) -> str:
    team = match.get(f"{side}_team") or {}
    return (team.get("name") or side.title()) if isinstance(team, dict) else side.title()
