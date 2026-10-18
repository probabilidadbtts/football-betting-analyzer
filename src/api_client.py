"""
Cliente HTTP para TheStatsAPI.
1000 req/min → sin throttle; backoff solo como red de seguridad.
"""
import time
import logging
import requests
from .config import API_KEY, BASE_URL, PER_PAGE, TIMEOUT

log = logging.getLogger(__name__)
H = {"Authorization": f"Bearer {API_KEY}", "Accept": "application/json"}


def _get(path: str, params: dict | None = None, retries: int = 2) -> dict:
    """GET con retry exponencial ante 429/5xx. Timeout de 10s.

    Mejora: maneja respuestas que no son JSON y errores en la decodificación JSON
    para evitar que r.json() lance excepciones no controladas que rompan el flujo
    y provoquen mensajes de log inesperados.
    """
    for attempt in range(retries):
        try:
            r = requests.get(f"{BASE_URL}{path}", headers=H, params=params, timeout=TIMEOUT)
        except requests.exceptions.Timeout:
            log.warning("TIMEOUT: GET %s (attempt %d)", path, attempt + 1)
            if attempt < retries - 1:
                time.sleep(1)
                continue
            return {}
        except requests.exceptions.RequestException as e:
            log.warning("ERROR: GET %s → %s", path, e)
            return {}

        # Rate limit / server errors
        if r.status_code == 429:
            wait = 2 ** attempt
            log.warning("429 rate-limit for %s, waiting %ss…", path, wait)
            time.sleep(wait)
            continue
        if r.status_code >= 500:
            log.warning("Server error %s: %s", r.status_code, r.text[:200])
            time.sleep(1)
            continue
        if r.status_code == 404:
            # Not found -> return empty payload
            log.debug("404 GET %s", path)
            return {}

        # At this point we expect a 2xx; ensure we surface HTTP errors
        try:
            r.raise_for_status()
        except requests.exceptions.HTTPError as e:
            log.warning("HTTP error GET %s → %s", path, e)
            return {}

        # Verificar content-type antes de parsear como JSON
        ct = r.headers.get("Content-Type", "")
        if "application/json" not in ct.lower():
            # Si la API devolvió un HTML/error, loguearlo de forma segura
            body_preview = r.text[:500].replace("\n", " ")
            log.warning("Non-JSON response for GET %s: status=%s content-type=%s body=%s", path, r.status_code, ct, body_preview)
            return {}

        try:
            return r.json()
        except ValueError:
            # JSON malformed
            body_preview = r.text[:500].replace("\n", " ")
            log.warning("Invalid JSON from GET %s: %s", path, body_preview)
            return {}

    return {}


# ─── Partidos ──────────────────────────────────────────────────────────


def matches(date_from: str,
            date_to: str | None = None,
            status: str | None = None,
            competition_id: str | None = None,
            team_id: str | None = None) -> list[dict]:
    """TODOS los partidos de la fecha. Paginación automática."""
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
        if team_id:
            params["team_id"] = team_id

        resp = _get("/football/matches", params)
        data = resp.get("data", [])
        meta = resp.get("meta", {})
        total_pages = meta.get("total_pages", 1)

        all_items.extend(data)
        if page >= total_pages:
            break
        page += 1

    return all_items


def team_recent_matches(team_id: str, n: int = 10, status: str = "finished") -> list[dict]:
    """Últimos N partidos terminados de un equipo."""
    return matches(date_from="2000-01-01", date_to="2099-12-31",
                   status=status, team_id=team_id)[:n]


# ─── Estadísticas + xG ──────────────────────────────────────────────────────


def match_stats(match_id: str) -> dict:
    resp = _get(f"/football/matches/{match_id}/stats")
    return resp.get("data", {})


# ─── Cuotas ───────────────────────────────────────────────────────────

def match_odds(match_id: str) -> dict:
    resp = _get(f"/football/matches/{match_id}/odds")
    return resp.get("data", {})


def match_odds_live(match_id: str) -> dict:
    resp = _get(f"/football/matches/{match_id}/odds/live")
    return resp.get("data", {})


# ─── Formaciones ─────────────────────────────────────────────────────────

def match_lineups(match_id: str) -> dict:
    resp = _get(f"/football/matches/{match_id}/lineups")
    return resp.get("data", {})


# ─── Plantilla de equipo ────────────────────────────────────────────────────

def team_players(team_id: str) -> list[dict]:
    resp = _get(f"/football/teams/{team_id}/players")
    data = resp.get("data", [])
    return data if isinstance(data, list) else []   
