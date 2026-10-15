"""Envío de mensajes a Telegram con formato por niveles."""
import logging
import requests
from .config import TELEGRAM_TOKEN, TELEGRAM_CHAT

log = logging.getLogger(__name__)


def _format_bet(bet: dict) -> str:
    """Formatea una apuesta para Telegram."""
    level_icons = {1: "🟢", 2: "🟡", 3: "🔴"}
    icon = level_icons.get(bet["level"], "⚪")

    line = (
        f"{icon} <b>{bet['home']} vs {bet['away']}</b>\n"
        f"   P={bet['p_model']:.0%} | Cuota={bet['btts_odds']:.2f} ({bet['btts_bookmaker']})"
    )
    if bet["value"]:
        line += f" | EV={bet['ev']:+.1f}%"
    if bet["stake"] > 0:
        line += f" | Stake={bet['stake']:.1f}u"

    # Detalles
    details = []
    details.append(f"λ: {bet['lambda_home']:.2f}-{bet['lambda_away']:.2f}")
    details.append(f"BTTS: {bet['home_btts_rate']:.0%}/{bet['away_btts_rate']:.0%}")
    details.append(f"xGA: {bet['home_xg_against']:.2f}/{bet['away_xg_against']:.2f}")
    if bet["h2h_btts"] is not None:
        details.append(f"H2H: {bet['h2h_btts']:.0%}")
    if bet["form_boost"] > 0:
        details.append("⬆️ Forma")
    if bet["home_absent"]:
        details.append(f"⚡ {bet['home_absent'][0]} ausente")
    if bet["away_absent"]:
        details.append(f"⚡ {bet['away_absent'][0]} ausente")

    line += "\n   " + " | ".join(details)
    return line


def send_analysis(results: list[dict], date_str: str, total_analyzed: int) -> None:
    """Envía el reporte completo a Telegram."""
    if not results:
        send(f"📭 Sin oportunidades por encima del umbral hoy ({date_str}).")
        return

    # Separar por nivel
    nivel1 = [r for r in results if r["level"] == 1 and r["filters_passed"]]
    nivel2 = [r for r in results if r["level"] == 2 and r["filters_passed"]]
    filtrados = [r for r in results if not r["filters_passed"]]

    # Ordenar por P descendente
    nivel1.sort(key=lambda x: -x["p_model"])
    nivel2.sort(key=lambda x: -x["p_model"])

    # Construir mensaje
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

    # Acumulador sugerido (top 3 Nivel 1)
    if len(nivel1) >= 3:
        top3 = nivel1[:3]
        acca_odds = 1.0
        acca_p = 1.0
        for b in top3:
            if b["btts_odds"]:
                acca_odds *= b["btts_odds"]
            acca_p *= b["p_model"]
        acca_ev = (acca_p * acca_odds - 1) * 100
        parts.append("═══ 🎯 ACUMULADOR SUGERIDO (Top 3) ═══\n")
        for b in top3:
            parts.append(f"  • {b['home']} vs {b['away']} @ {b['btts_odds']:.2f}")
        parts.append(f"  Cuota total: {acca_odds:.2f} | P: {acca_p:.0%} | EV: {acca_ev:+.1f}%\n")

    # Filtrados (resumen)
    if filtrados:
        parts.append("═══ ⛔ FILTRADOS ═══\n")
        for b in filtrados[:5]:
            reason = b["filter_reasons"][0] if b["filter_reasons"] else "?"
            parts.append(f"  • {b['home']} vs {b['away']} → {reason}")
        if len(filtrados) > 5:
            parts.append(f"  …y {len(filtrados) - 5} más")

    msg = "\n".join(parts)

    # Truncar a 4000 chars
    if len(msg) > 4000:
        msg = msg[:3997] + "..."

    send(msg)


def send(text: str) -> None:
    """Envía un mensaje HTML a Telegram."""
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
