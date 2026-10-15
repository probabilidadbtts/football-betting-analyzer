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
PROB_THRESHOLD_SINGLE = 0.68    # Mínimo para singles
PROB_THRESHOLD_ACCA   = 0.72    # Mínimo para acumuladores
VALUE_MARGIN          = 0.03    # Margen de value mínimo (3%)
MAX_ACCA_PICKS        = 4       # Máximo de selecciones en acumulador

# ─── Filtros estadísticos ────────────────────────────────────────────────────
BTTS_RATE_MIN         = 0.55   # Tasa BTTS mínima (últimos 10)
XGA_MIN               = 1.20   # xGA mínimo por equipo
CLEAN_SHEET_MAX       = 0.35   # Tasa clean sheets máxima
CLEAN_SHEET_AWAY_MAX  = 0.45   # Tasa clean sheets visitante máxima (descartar)
REST_DAYS_MIN         = 3      # Días de descanso mínimos

# ─── Modelo Poisson ──────────────────────────────────────────────────────────
POISSON_MAX_GOALS     = 8      # Máximo de goles en matriz de scores

# ─── Kelly ───────────────────────────────────────────────────────────────────
KELLY_FRACTION        = 0.25   # ¼ Kelly (reducir varianza)
BANKROLL_UNITS        = 100    # Bankroll en unidades

# ─── Paralelismo ─────────────────────────────────────────────────────────────
MAX_WORKERS           = 10
MAX_MATCHES           = 300
PER_PAGE              = 100
TIMEOUT               = 10     # segundos por request   
