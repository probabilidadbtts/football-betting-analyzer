import os

# ─── API ───────────────────────────────────────────────
API_KEY  = os.environ["THESTATSAPI_API_KEY"]
BASE_URL = "https://api.thestatsapi.com/api"

# ─── Telegram ──────────────────────────────────────────
TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT  = os.environ["TELEGRAM_CHAT_ID"]

# ─── Filtro opcional de competiciones ──────────────────
# Vacío = TODAS las competiciones (recomendado).
COMPETITION_IDS: list[str] = []

# ─── Umbral de probabilidad implícita mínima ───────────
PROB_THRESHOLD = 0.62

# ─── Boost por forma reciente ──────────────────────────
FORM_BOOST = 0.05

# ─── Penalización por ausencia de delantero clave ──────
ABSENCE_PENALTY = 0.05

# ─── Penalización xGA (defensa sólida del rival) ───────
# xGA < 0.70 → -12%
# xGA < 0.90 → -8%
XGA_PENALTY_LOW  = -0.12
XGA_PENALTY_HIGH = -0.08
XGA_THRESHOLD_LOW  = 0.70
XGA_THRESHOLD_HIGH = 0.90

# ─── Límite de partidos a analizar por ejecución ──────
MAX_MATCHES = 300

# ─── Per-page para paginación ──────────────────────────
PER_PAGE = 100

# ─── Paralelismo ───────────────────────────────────────
MAX_WORKERS = 10   
