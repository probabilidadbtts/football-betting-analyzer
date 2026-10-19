"""
Cliente TheStatsAPI: form home/away, xG, lesiones y plantilla.
"""
from __future__ import annotations

import logging
import time
from typing import Any
from datetime import datetime, timedelta, timezone
import requests

from .config import API_KEY, BASE_URL, PER_PAGE, TIMEOUT, MAX_RETRIES

log = logging.getLogger(__name__)

_HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json",
    "User-Agent": "football-betting-analyzer/2.3",
}

_team_matches_cache: dict[str, list[dict]] = {}
_stats_cache: dict[str, dict] = {}
_squad_cache: dict[str, list[dict]] = {}


def _get(path: str, params: dict | None = None, retries: int = MAX_RETRIES) -> dict:
    url = f"{BASE_URL}{path}"
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=_HEADERS, params=params or {}, timeout=TIMEOUT)
        except requests.exceptions.Timeout:
            if attempt < retries - 1:
                time.sleep(1.8 ** attempt)
                continue
            return {}
        except requests.exceptions.RequestException:
            if attempt < retries - 1:
                time.sleep(1.5 ** attempt)
                continue
            return {}

        if r.status_code == 429:
            retry_after = int(r.headers.get("Retry-After", min(30, 2 ** attempt + 1)))
            time.sleep(retry_after)
            continue
        if r.status_code >= 500:
            time.sleep(1.6 ** attempt)
            continue
        if r.status_code in (404, 409, 401):
            return {}
        try:
            r.raise_for_status()
            return r.json()
        except Exception:
            return {}
    return {}


def matches(
    date_from: str,
    date_to: str | None = None,
    status: str | None = None,
    competition_id: str | None = None,
    team_id: str | None = None,
    sort: str = "utc_date",
    per_page: int = PER_PAGE,
) -> list[dict]:
    date_to = date_to or date_from
    all_items: list[dict] = []
    page = 1
    while True:
        params: dict[str, Any] = {
            "date_from": date_from,
            "date_to": date_to,
            "per_page": min(per_page, 100),
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
        if page % 4 == 0:
            time.sleep(0.25)
    return all_items


def team_finished_matches(team_id: str, n: int = 30) -> list[dict]:
    if not team_id:
        return []
    if team_id in _team_matches_cache:
        return _team_matches_cache[team_id][:n]
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=160)
    items = matches(
        date_from=start.isoformat(),
        date_to=end.isoformat(),
        status="finished",
        team_id=team_id,
        sort="-utc_date",
        per_page=50,
    )
    items = sorted(items, key=lambda m: m.get("utc_date") or "", reverse=True)
    _team_matches_cache[team_id] = items
    return items[:n]


def team_home_matches(team_id: str, n: int = 5) -> list[dict]:
    """Últimos N partidos del equipo como LOCAL."""
    all_m = team_finished_matches(team_id, n=30)
    out = []
    for m in all_m:
        if team_id_from_match(m, "home") == team_id:
            out.append(m)
            if len(out) >= n:
                break
    return out


def team_away_matches(team_id: str, n: int = 5) -> list[dict]:
    """Últimos N partidos del equipo como VISITANTE."""
    all_m = team_finished_matches(team_id, n=30)
    out = []
    for m in all_m:
        if team_id_from_match(m, "away") == team_id:
            out.append(m)
            if len(out) >= n:
                break
    return out


def match_stats(match_id: str) -> dict:
    if not match_id:
        return {}
    if match_id in _stats_cache:
        return _stats_cache[match_id]
    resp = _get(f"/football/matches/{match_id}/stats")
    data = resp.get("data") or {}
    if data:
        _stats_cache[match_id] = data
    return data


def match_live_stats(match_id: str) -> dict:
    return (_get(f"/football/matches/{match_id}/live-stats") or {}).get("data") or {}


def match_odds(match_id: str) -> dict:
    return (_get(f"/football/matches/{match_id}/odds") or {}).get("data") or {}


def match_odds_live(match_id: str) -> dict:
    return (_get(f"/football/matches/{match_id}/odds/live") or {}).get("data") or {}


def team_injuries_suspensions(team_id: str, current: bool = True) -> dict:
    if not team_id:
        return {}
    resp = _get(f"/football/teams/{team_id}/injuries-suspensions", {"current": str(current).lower()})
    return resp.get("data") or {}


def team_squad(team_id: str) -> list[dict]:
    if not team_id:
        return []
    if team_id in _squad_cache:
        return _squad_cache[team_id]
    resp = _get(f"/football/teams/{team_id}/players")
    data = resp.get("data") or []
    if isinstance(data, list):
        _squad_cache[team_id] = data
        return data
    return []


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
    return None


def team_id_from_match(match: dict, side: str) -> str:
    team = match.get(f"{side}_team") or {}
    return str(team.get("id") or "") if isinstance(team, dict) else ""


def team_name_from_match(match: dict, side: str) -> str:
    team = match.get(f"{side}_team") or {}
    return str(team.get("name") or side.title()) if isinstance(team, dict) else side.title()


def extract_live_match_state(match: dict, live_stats: dict) -> tuple[int, int, int]:
    minute = 0
    for source in (match, live_stats):
        if not isinstance(source, dict):
            continue
        for key in ("minute", "elapsed", "time"):
            if key in source and source[key] is not None:
                try:
                    minute = int(float(source[key]))
                    break
                except (ValueError, TypeError):
                    continue
        if minute:
            break
    if minute <= 0:
        minute = 45
    sh = safe_score(match, "home")
    sa = safe_score(match, "away")
    return max(0, min(95, minute)), int(sh or 0), int(sa or 0)
