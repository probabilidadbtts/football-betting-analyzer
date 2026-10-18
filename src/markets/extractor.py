"""
Extracción y agregación de cuotas de múltiples bookmakers.
Busca la mejor cuota (mayor) para cada selección → maximiza edge real.
"""
from __future__ import annotations

from statistics import mean
from typing import Any


def _f(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, dict):
        for key in ("last_seen", "current", "live", "price", "opening"):
            if key in v and v[key] is not None:
                try:
                    return float(v[key])
                except (TypeError, ValueError):
                    continue
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _d(v: Any) -> dict:
    return v if isinstance(v, dict) else {}


def extract_all_odds(odds_payload: dict) -> dict[str, list[tuple[float, str]]]:
    """
    Extrae todas las cuotas disponibles de todos los bookmakers.
    Retorna: { market_key: [(odds, bookmaker_name), ...] }
    """
    result: dict[str, list[tuple[float, str]]] = {
        "btts_yes": [], "btts_no": [],
        "over_25": [], "under_25": [],
        "home_win": [], "draw": [], "away_win": [],
        "home_dnb": [], "away_dnb": [],
        "dc_1x": [], "dc_12": [], "dc_x2": [],
    }

    bookmakers = odds_payload.get("bookmakers") or []
    if not isinstance(bookmakers, list):
        return result

    for bk in bookmakers:
        if not isinstance(bk, dict):
            continue
        name = bk.get("bookmaker") or bk.get("name") or "?"
        markets = _d(bk.get("markets"))

        # BTTS
        btts = _d(markets.get("btts"))
        yes = _f(btts.get("yes"))
        no = _f(btts.get("no"))
        if yes and yes > 1.01:
            result["btts_yes"].append((yes, name))
        if no and no > 1.01:
            result["btts_no"].append((no, name))

        # Total goals 2.5
        tg = _d(markets.get("total_goals"))
        line_25 = _d(tg.get("2.5") or tg.get("2,5"))
        over = _f(line_25.get("over"))
        under = _f(line_25.get("under"))
        if over and over > 1.01:
            result["over_25"].append((over, name))
        if under and under > 1.01:
            result["under_25"].append((under, name))

        # Match odds (1X2)
        mo = _d(markets.get("match_odds"))
        h = _f(mo.get("home"))
        d = _f(mo.get("draw"))
        a = _f(mo.get("away"))
        if h and h > 1.01:
            result["home_win"].append((h, name))
        if d and d > 1.01:
            result["draw"].append((d, name))
        if a and a > 1.01:
            result["away_win"].append((a, name))

        # Draw No Bet
        dnb = _d(markets.get("draw_no_bet"))
        dh = _f(dnb.get("home"))
        da = _f(dnb.get("away"))
        if dh and dh > 1.01:
            result["home_dnb"].append((dh, name))
        if da and da > 1.01:
            result["away_dnb"].append((da, name))

        # Double chance
        dc = _d(markets.get("double_chance"))
        d1x = _f(dc.get("home_draw") or dc.get("1x"))
        d12 = _f(dc.get("home_away") or dc.get("12"))
        dx2 = _f(dc.get("draw_away") or dc.get("x2"))
        if d1x and d1x > 1.01:
            result["dc_1x"].append((d1x, name))
        if d12 and d12 > 1.01:
            result["dc_12"].append((d12, name))
        if dx2 and dx2 > 1.01:
            result["dc_x2"].append((dx2, name))

    return result


def best_odds(candidates: list[tuple[float, str]]) -> tuple[float | None, str]:
    """Devuelve (mejor_cuota, bookmaker)."""
    if not candidates:
        return None, ""
    candidates = sorted(candidates, key=lambda x: x[0], reverse=True)
    return candidates[0]


def market_implied_prob(candidates: list[tuple[float, str]], top_n: int = 3) -> float | None:
    """Probabilidad implícita promedio de las top-N mejores cuotas."""
    if not candidates:
        return None
    top = sorted(candidates, key=lambda x: x[0], reverse=True)[:top_n]
    probs = [1.0 / o for o, _ in top if o > 1.0]
    return mean(probs) if probs else None
