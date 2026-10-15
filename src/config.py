import os

# ─── API ─────────────────────────────────────────────────────────────────────
API_KEY  = os.environ["THESTATSAPI_API_KEY"]
BASE_URL = "https://api.thestatsapi.com/api"

# ─── Telegram ────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT  = os.environ["TELEGRAM_CHAT_ID"]

# ─── Filtro opcional de competiciones (vacío = TODAS) ────────────────────────
COMPETITION_IDS: list[str] = []

# ─── Umbrales ────────────────────────────────────────────────────────────────
PROB_THRESHOLD_SINGLE = 0.68
PROB_THRESHOLD_ACCA   = 0.72
VALUE_MARGIN          = 0.03
MAX_ACCA_PICKS        = 4

# ─── Boosts y penalizaciones ─────────────────────────────────────────────────
FORM_BOOST            = 0.05
ABSENCE_PENALTY       = 0.05

# ─── Filtros estadísticos ────────────────────────────────────────────────────
BTTS_RATE_MIN         = 0.55
XGA_MIN               = 1.20
CLEAN_SHEET_MAX       = 0.35
CLEAN_SHEET_AWAY_MAX  = 0.45
REST_DAYS_MIN         = 3

# ─── Modelo Poisson ──────────────────────────────────────────────────────────
POISSON_MAX_GOALS     = 8

# ─── Kelly ───────────────────────────────────────────────────────────────────
KELLY_FRACTION        = 0.25
BANKROLL_UNITS        = 100

# ─── Paralelismo ─────────────────────────────────────────────────────────────
MAX_WORKERS           = 10
MAX_MATCHES           = 300
PER_PAGE              = 100
TIMEOUT               = 10   
