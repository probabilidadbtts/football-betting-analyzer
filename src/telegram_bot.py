"""
Notificaciones claras para Telegram, priorizando apuestas de valor individuales.
"""
from __future__ import annotations

import logging
import requests
from .config import TELEGRAM_TOKEN, TELEGRAM_CHAT

log = logging.getLogger(__name__)

ICONS = {1: "🟢 [L1-ALTO VALOR]", 2: "🟡 [L2-VALOR]"}


def format_card(m: dict, p: dict) -> str:
    header = f"{ICONS.get(p['level'], '⚪')} <b>{m['home']} vs {m['away']}</b>"
    if m.get("is_live"):
        header += f" (LIVE {m.get('minute')}' | {m.get('score_str')})"

    body = (
        f"\n🎯 <b>{p['market_label']}</b> @ <b>{p['odds']:.2f}</b> ({p['bookmaker']})\n"
        f"📊 P.Est: <b>{p['p_final']:.1%}</b> | Edge: <b>{p['edge']:+.1%}</b> | EV: <b>{p['ev']:+.1f}%</b>\n"
        f"💰 Stake Sugerido: <b>{p['stake']}u</b> (Criterio Kelly Fraccional)\n"
        f"⚙️ λ Local: {m['lambda_home']} | λ Visitante: {m['lambda_away']}"
    )
    if p.get("context_reasons"):
        body += f"\n💡 Contexto: {' · '.join(p['context_reasons'][:2])}"
    return header + body


def send_report(results: list[dict], title: str, total_analyzed: int) -> None:
    l1: list[tuple[dict, dict]] = []
    l2: list[tuple[dict, dict]] = []

    for r in results:
        if not r or not r.get("has_value"):
            continue
        for pick in r["value_picks"]:
            if pick["level"] == 1:
                l1.append((r, pick))
            elif pick["level"] == 2:
                l2.append((r, pick))

    l1.sort(key=lambda x: -x[1]["edge"])
    l2.sort(key=lambda x: -x[1]["edge"])

    lines = [
        f"⚽ <b>{title}</b>",
        f"📈 Partidos analizados: <b>{total_analyzed}</b> | Picks L1: <b>{len(l1)}</b> | Picks L2: <b>{len(l2)}</b>\n",
    ]

    if not l1 and not l2:
        lines.append("🛡️ <i>No se detectaron ventajas matemáticas con margen suficiente hoy.</i>")
        _dispatch("\n".join(lines))
        return

    if l1:
        lines.append("<b>════ 🟢 NIVEL 1: MÁXIMA CONVICCIÓN ════</b>")
        for match, pick in l1[:8]:
            lines.append(format_card(match, pick) + "\n")

    if l2:
        lines.append("<b>════ 🟡 NIVEL 2: VALOR SECUNDARIO ════</b>")
        for match, pick in l2[:6]:
            lines.append(format_card(match, pick) + "\n")

    _dispatch("\n".join(lines))


def _dispatch(text: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        log.info("Telegram no configurado. Log local:\n%s", text[:400])
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT,
        "text": text[:3900],
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, json=payload, timeout=20)
        r.raise_for_status()
    except Exception as e:
        log.error("Fallo al enviar a Telegram: %s", e)
