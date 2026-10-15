"""Envío de mensajes a Telegram con formato por niveles."""
import logging
import requests
from .config import TELEGRAM_TOKEN, TELEGRAM_CHAT

log = logging.getLogger(__name__)


def _d(v) -> dict:
    return v if isinstance(v, dict) else {}


def _format_bet(bet: dict) -> str:
    level_icons = {1: "🟢", 2: "🟡", 3: "🔴"}
    icon = level_icons.get(bet.get("level", 3), "⚪")

    odds = bet.get("btts_odds") or 0
    line = (
        f"{icon} <b>{bet.get('home','?')} vs {bet.get('away','?')}</b>\n"
        f"   P={bet.get('p_model',0):.0%} | Cuota={odds:.2f} ({bet.get('btts_bookmaker','?')})"
    )
    if bet.get("value"):
        line += f" | EV={bet.get('ev',0):+.1f}%"
    if bet.get("stake", 0) > 0:
        line += f" | Stake={bet['stake']:.1f}u"

    details = []
    details.append(f"λ: {bet.get('lambda_home',0):.2f}-{bet.get('lambda_away',0):.2f}")
    details.append(f"BTTS: {bet.get('home_btts_rate',0):.0%}/{bet.get('away_btts_rate',0):.0%}")
    details.append(f"xGA: {bet.get('home_xg_against',0):.2f}/{bet.get('away_xg_against',0):.2f}")
    if bet.get("h2h_btts") is not None:
        details.append(f"H2H: {bet['h2h_btts']:.0%}")
    if bet.get("form_boost", 0) > 0:
        details.append("⬆️ Forma")
    if bet.get("home_absent"):
        details.append(f"⚡ {bet['home_absent'][0]} ausente")
    if bet.get("away_absent"):
        details.append(f"⚡ {bet['away_absent'][0]} ausente")

    line += "\n   " + " | ".join(details)
    return line


def send_analysis(results: list[dict], date_str: str, total_analyzed: int) -> None:
    if not results:
        send(f"📭 Sin oportunidades por encima del umbral hoy ({date_str}).")
        return

    nivel1 = [r for r in results if r.get("level") == 1 and r.get("filters_passed")]
    nivel2 = [r for r in results if r.get("level") == 2 and r.get("filters_passed")]
    filtrados = [r for r in results if not r.get("filters_passed")]

    nivel1.sort(key=lambda x: -x.get("p_model", 0))
    nivel2.sort(key=lambda x: -x.get("p_model", 0))

    parts = [f"🏆 <b>ANÁLISIS BTTS — {date_str}</b>\n"]
    parts.append(f"📊 {total_analyzed} partidos | 🟢 {len(nivel1)} | 🟡 {len(nivel2)} | ⛔ {len(filtrados)} filtrados\n")

    if nivel1:
        parts.append("═══ 🟢 NIVEL 1 (Máximo Valor) ═══\n")
        for b in nivel1[:10]:
            parts.append(_format_bet(b) + "\n")

    if nivel2:
        parts.append("═══ 🟡 NIVEL 2 (Intermedio) ═══\n")
        for b in nivel2[:10]:
            parts.append(_format_bet(b) + "\n")

    if len(nivel1) >= 3:
        top3 = nivel1[:3]
        acca_odds = 1.0
        acca_p = 1.0
        for b in top3:
            if b.get("btts_odds"):
                acca_odds *= b["btts_odds"]
            acca_p *= b.get("p_model", 0)
        acca_ev = (acca_p * acca_odds - 1) * 100
        parts.append("═══ 🎯 ACUMULADOR SUGERIDO (Top 3) ═══\n")
        for b in top3:
            parts.append(f"  • {b.get('home','?')} vs {b.get('away','?')} @ {b.get('btts_odds',0):.2f}")
        parts.append(f"  Cuota total: {acca_odds:.2f} | P: {acca_p:.0%} | EV: {acca_ev:+.1f}%\n")

    if filtrados:
        parts.append("═══ ⛔ FILTRADOS ═══\n")
        for b in filtrados[:5]:
            reasons = b.get("filter_reasons", [])
            reason = reasons[0] if reasons else "?"
            parts.append(f"  • {b.get('home','?')} vs {b.get('away','?')} → {reason}")
        if len(filtrados) > 5:
            parts.append(f"  …y {len(filtrados) - 5} más")

    msg = "\n".join(parts)
    if len(msg) > 4000:
        msg = msg[:3997] + "..."

    send(msg)


def send(text: str) -> None:
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
        log.info("Telegram: mensaje enviado (%d chars)", len(text))
    except Exception as e:
        log.error("Error enviando a Telegram: %s", e)
        raise   
