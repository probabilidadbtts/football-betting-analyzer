"""
Extracción de cuotas y cálculo de probabilidades de mercado justas
mediante desmargenación proporcional (un-vigging) completa.
"""
from __future__ import annotations

from typing import Any
from ..config import SHARP_BOOKMAKERS


def _parse_float(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, dict):
        for k in ("last_seen", "current", "price", "decimal", "value"):
            if k in v and v[k] is not None:
                try:
                    return float(v[k])
                except (ValueError, TypeError):
                    pass
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def devig_proportional(odds_dict: dict[str, float]) -> dict[str, float]:
    """Elimina el overround de una casa de apuestas de forma proporcional."""
    inv_sum = sum(1.0 / od for od in odds_dict.values() if od > 1.0)
    if inv_sum <= 0:
        return {}
    return {k: (1.0 / od) / inv_sum for k, od in odds_dict.items() if od > 1.0}


def extract_and_devig_markets(odds_payload: dict) -> tuple[dict[str, tuple[float, str]], dict[str, float]]:
    """
    Retorna:
      - best_odds: { "market_key": (mejor_cuota_disponible, nombre_bookmaker) }
      - fair_market_probs: { "market_key": probabilidad_justa_consenso_sin_margen }
    """
    bookmakers = odds_payload.get("bookmakers") or []
    if not isinstance(bookmakers, list):
        return {}, {}

    best_odds: dict[str, tuple[float, str]] = {}
    fair_samples: dict[str, list[tuple[float, float]]] = {}  # {mkt: [(fair_prob, weight)]}

    def _track_best(m_key: str, od: float, bk_name: str):
        if od > 1.01:
            if m_key not in best_odds or od > best_odds[m_key][0]:
                best_odds[m_key] = (od, bk_name)

    for bk in bookmakers:
        if not isinstance(bk, dict):
            continue
        name = str(bk.get("bookmaker") or bk.get("name") or "unknown").lower()
        mkts = bk.get("markets") or {}
        weight = 2.0 if any(s in name for s in SHARP_BOOKMAKERS) else 1.0

        # 1. Match Odds (1X2)
        mo = mkts.get("match_odds") or {}
        h, d, a = _parse_float(mo.get("home")), _parse_float(mo.get("draw")), _parse_float(mo.get("away"))
        if h and d and a:
            _track_best("home_win", h, name)
            _track_best("draw", d, name)
            _track_best("away_win", a, name)
            dev = devig_proportional({"home_win": h, "draw": d, "away_win": a})
            for k, p in dev.items():
                fair_samples.setdefault(k, []).append((p, weight))

        # 2. Over / Under 2.5
        tg = mkts.get("total_goals") or {}
        line_25 = tg.get("2.5") or tg.get("2,5") or {}
        ov, un = _parse_float(line_25.get("over")), _parse_float(line_25.get("under"))
        if ov and un:
            _track_best("over_25", ov, name)
            _track_best("under_25", un, name)
            dev = devig_proportional({"over_25": ov, "under_25": un})
            for k, p in dev.items():
                fair_samples.setdefault(k, []).append((p, weight))

        # 3. Both Teams To Score (BTTS)
        btts = mkts.get("btts") or {}
        by, bn = _parse_float(btts.get("yes")), _parse_float(btts.get("no"))
        if by and bn:
            _track_best("btts_yes", by, name)
            _track_best("btts_no", bn, name)
            dev = devig_proportional({"btts_yes": by, "btts_no": bn})
            for k, p in dev.items():
                fair_samples.setdefault(k, []).append((p, weight))

        # 4. Double Chance
        dc = mkts.get("double_chance") or {}
        d1x = _parse_float(dc.get("home_draw") or dc.get("1x"))
        dx2 = _parse_float(dc.get("draw_away") or dc.get("x2"))
        d12 = _parse_float(dc.get("home_away") or dc.get("12"))
        if d1x: _track_best("dc_1x", d1x, name)
        if dx2: _track_best("dc_x2", dx2, name)
        if d12: _track_best("dc_12", d12, name)

        # 5. Draw No Bet
        dnb = mkts.get("draw_no_bet") or {}
        dh, da = _parse_float(dnb.get("home")), _parse_float(dnb.get("away"))
        if dh: _track_best("home_dnb", dh, name)
        if da: _track_best("away_dnb", da, name)

    # Calcular promedio ponderado de probabilidades justas (de-vigged)
    fair_market_probs: dict[str, float] = {}
    for m_key, samples in fair_samples.items():
        total_w = sum(w for _, w in samples)
        if total_w > 0:
            fair_market_probs[m_key] = sum(p * w for p, w in samples) / total_w

    # Derivadas de 1X2 si no existen directas
    if "home_win" in fair_market_probs and "draw" in fair_market_probs and "away_win" in fair_market_probs:
        ph = fair_market_probs["home_win"]
        pd = fair_market_probs["draw"]
        pa = fair_market_probs["away_win"]
        fair_market_probs.setdefault("dc_1x", ph + pd)
        fair_market_probs.setdefault("dc_x2", pd + pa)
        fair_market_probs.setdefault("dc_12", ph + pa)
        if (ph + pa) > 1e-5:
            fair_market_probs.setdefault("home_dnb", ph / (ph + pa))
            fair_market_probs.setdefault("away_dnb", pa / (ph + pa))

    return best_odds, fair_market_probs
