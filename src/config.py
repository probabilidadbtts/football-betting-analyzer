import os

# ─── API ───────────────────────────────────────────────
API_KEY  = os.environ["THESTATSAPI_API_KEY"]
BASE_URL = "https://api.thestatsapi.com/api"

# ─── Telegram ──────────────────────────────────────────
TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT  = os.environ["TELEGRAM_CHAT_ID"]

# ─── Filtro opcional de competiciones ──────────────────
# Vacío = TODAS las competiciones (recomendado).
# Si quieres limitar, agrega IDs: ["comp_3039", "comp_1", ...]
COMPETITION_IDS: list[str] = []

# ─── Umbral de probabilidad implícita mínima ───────────
PROB_THRESHOLD = 0.60

# ─── Boost por forma reciente ──────────────────────────
FORM_BOOST = 0.05

# ─── Penalización por ausencia de delantero clave ──────
ABSENCE_PENALTY = 0.05

# ─── Límite de partidos a analizar por ejecución ──────
MAX_MATCHES = 300

# ─── Per-page para paginación ──────────────────────────
PER_PAGE = 100   
