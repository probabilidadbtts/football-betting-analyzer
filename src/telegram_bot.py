"""Envío de análisis multi-mercado a Telegram con formato claro."""
from __future__ import annotations

import logging
import requests
from .config import TELEGRAM_TOKEN, TELEGRAM_CHAT

log = logging.getLogger(__name__)

LEVEL_ICON = {1: "🟢", 2: "🟡", 3: "🔴"}


def _format_pick(match: dict, pick: dict) -> str:
    icon = LEVEL_ICON.get(pick.get("level", 3), "⚪")
    line = (
        f"{icon} <b>{match.get('home','?')} vs {match.get('away','?')}</b>\n"
        f"   <b>{pick.get('market_label')}</b> @ {pick.get('odds',0):.2f} "
        f"({pick.get('bookmaker','?')})\n"
        f"   P={pick.get('p_model',0):.0%} | Edge={pick.get('edge',0):+.1%} | "
        f"EV={pick.get('ev',0):+.1f}% | Stake={pick.get('stake',0):.1f}u | "
        f"Ctx={pick.get('context_score',0):.0f}"
    )
    details = []
    details.append(f"λ {match.get('lambda_home',0):.2f}-{match.get('lambda_away',0):.2f}")
    details.append(f"BTTS {match.get('home_btts_rate',0):.0%}/{match.get('away_btts_rate',0):.0%}")
    details.append(f"xGA {match.get('home_xg_against',0):.2f}/{match.get('away_xg_against',0):.2f}")
    if match.get("h2h"):
        details.append(f"H2H BTTS {match['h2h'].get('btts_rate',0):.0%}")
    if match.get("home_absences", 0) or match.get("away_absences", 0):
        details.append(f"Bajas {match.get('home_absences',0)}/{match.get('away_absences',0)}")
    reasons = pick.get("context_reasons") or []
    if reasons:
        details.append(" · ".join(reasons[:2]))
    line += "\n   " + " | ".join(details)
    return line


def send_analysis(results: list[dict], date_str: str, total_analyzed: int) -> None:
    """results = lista de outputs de analyze()."""
    level1: list[tuple[dict, dict]] = []
    level2: list[tuple[dict, dict]] = []

    for r in results:
        if not r or not r.get("has_value"):
            continue
        for p in r.get("value_picks") or []:
            if p.get("level") == 1:
                level1.append((r, p))
            elif p.get("level") == 2:
                level2.append((r, p))

    level1.sort(key=lambda x: -x[1].get("edge", 0))
    level2.sort(key=lambda x: -x[1].get("edge", 0))

    parts = [
        f"🏆 <b>VALUE FINDER — {date_str}</b>\n",
        f"📊 {total_analyzed} partidos analizados | "
        f"🟢 {len(level1)} L1 | 🟡 {len(level2)} L2\n",
    ]

    if not level1 and not level2:
        parts.append("\n📭 Sin oportunidades de valor que superen umbrales hoy.")
        send("\n".join(parts))
        return

    if level1:
        parts.append("═══ 🟢 NIVEL 1 — Máximo valor ═══\n")
        for match, pick in level1[:12]:
            parts.append(_format_pick(match, pick) + "\n")

    if level2:
        parts.append("═══ 🟡 NIVEL 2 — Intermedio ═══\n")
        for match, pick in level2[:10]:
            parts.append(_format_pick(match, pick) + "\n")

    if len(level1) >= 2:
        top = level1[:3]
        acca_odds = 1.0
        acca_p = 1.0
        parts.append("═══ 🎯 ACUMULADOR SUGERIDO ═══\n")
        for match, pick in top:
            acca_odds *= pick.get("odds") or 1.0
            acca_p *= pick.get("p_model") or 0.5
            parts.append(
                f"  • {match.get('home','?')} vs {match.get('away','?')} "
                f"— {pick.get('market_label')} @ {pick.get('odds',0):.2f}"
            )
        acca_ev = (acca_p * acca_odds - 1) * 100
        parts.append(
            f"\n  Cuota combinada: {acca_odds:.2f} | "
            f"P≈{acca_p:.0%} | EV≈{acca_ev:+.1f}%\n"
        )

    msg = "\n".join(parts)
    if len(msg) > 4000:
        msg = msg[:3990] + "\n…"
    send(msg)


def send(text: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        log.warning("Telegram no configurado (faltan token/chat_id). Mensaje no enviado.")
        log.info("Preview:\n%s", text[:500])
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, data=payload, timeout=30)
        r.raise_for_status()
        log.info("Telegram OK (%d chars)", len(text))
    except Exception as e:
        log.error("Error Telegram: %s", e)
        raise
