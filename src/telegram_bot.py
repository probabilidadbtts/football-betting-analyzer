"""Envío de mensajes a Telegram."""
import logging
import requests
from .config import TELEGRAM_TOKEN, TELEGRAM_CHAT

log = logging.getLogger(__name__)


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
