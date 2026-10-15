"""
Cliente HTTP para TheStatsAPI.
1000 req/min → sin throttle; backoff solo como red de seguridad.
"""
import time
import logging
import requests
from .config import API_KEY, BASE_URL, PER_PAGE

log = logging.getLogger(__name__)
H = {"Authorization": f"Bearer {API_KEY}", "Accept": "application/json"}


def _get(path: str, params: dict | None = None, retries: int = 3) -> dict:
    """GET con retry exponencial ante 429/5xx."""
    for attempt in range(retries):
        r = requests.get(f"{BASE_URL}{path}", headers=H, params=params, timeout=30)
        if r.status_code == 429:
            wait = 2 ** attempt
            log.warning("429 rate-limit, esperando %ss…", wait)
            time.sleep(wait)
            continue
        if r.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"Exhausted {retries} retries: GET {path}")


# ─── Partidos ───────────────────────────────────────────────────────────────

def matches(date_from: str,
            date_to: str | None = None,
            status: str | None = None,
            competition_id: str | None = None) -> list[dict]:
    """
    Devuelve TODOS los partidos de la fecha (todas las competiciones).
    Paginación automática.
    
    Parámetros:
        date_from: "YYYY-MM-DD"
        date_to:   "YYYY-MM-DD" (default: mismo que date_from)
        status:    "scheduled" | "live" | "finished" | "postponed" | None
        competition_id: opcional, para filtrar una liga específica
    """
    date_to = date_to or date_from
    all_items: list[dict] = []
    page = 1

    while True:
        params: dict = {
            "date_from": date_from,
            "date_to": date_to,
            "per_page": PER_PAGE,
            "page": page,
        }
        if status:
            params["status"] = status
        if competition_id:
            params["competition_id"] = competition_id

        resp = _get("/football/matches", params)
        data = resp.get("data", [])
        meta = resp.get("meta", {})
        total_pages = meta.get("total_pages", 1)

        all_items.extend(data)
        log.debug("  page %d/%d → %d partidos (total: %d)",
                  page, total_pages, len(data), len(all_items))

        if page >= total_pages:
            break
        page += 1

    return all_items


# ─── Estadísticas + xG ──────────────────────────────────────────────────────

def match_stats(match_id: str) -> dict:
    resp = _get(f"/football/matches/{match_id}/stats")
    return resp.get("data", {})


# ─── Cuotas ─────────────────────────────────────────────────────────────────

def match_odds(match_id: str) -> dict:
    resp = _get(f"/football/matches/{match_id}/odds")
    return resp.get("data", {})


def match_odds_live(match_id: str) -> dict:
    resp = _get(f"/football/matches/{match_id}/odds/live")
    return resp.get("data", {})


# ─── Formaciones ────────────────────────────────────────────────────────────

def match_lineups(match_id: str) -> dict:
    resp = _get(f"/football/matches/{match_id}/lineups")
    return resp.get("data", {})


# ─── Plantilla de equipo ────────────────────────────────────────────────────

def team_players(team_id: str) -> list[dict]:
    resp = _get(f"/football/teams/{team_id}/players")
    data = resp.get("data", [])
    return data if isinstance(data, list) else []


# ─── Forma reciente (últimos N partidos de un equipo) ───────────────────────

def team_recent_matches(team_id: str, n: int = 5) -> list[dict]:
    """Últimos N partidos terminados de un equipo."""
    all_items: list[dict] = []
    page = 1
    while True:
        params = {
            "team_id": team_id,
            "status": "finished",
            "per_page": n,
            "page": page,
        }
        resp = _get("/football/matches", params)
        data = resp.get("data", [])
        all_items.extend(data)
        meta = resp.get("meta", {})
        if page >= meta.get("total_pages", 1):
            break
        page += 1
    return all_items[:n]   
