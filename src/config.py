"""
Configuración central del analizador de value betting.
Todos los umbrales y pesos están aquí para facilitar backtesting y ajuste.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ─── API ────────────────────────────────────────────────────────────
API_KEY   = os.getenv("THESTATSAPI_API_KEY", "")
BASE_URL  = "https://api.thestatsapi.com/api"
TIMEOUT   = 12
PER_PAGE  = 100
MAX_RETRIES = 3

# ─── Telegram ───────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")

# ─── Competiciones (vacío = TODAS las que tengan odds) ──────────────
# Ejemplo: ["comp_3039", "comp_8814"]  # Premier + LaLiga
COMPETITION_IDS: list[str] = []

# ─── Mercados a analizar ────────────────────────────────────────────
MARKETS = {
    "btts_yes":        "BTTS Yes",
    "over_25":         "Over 2.5",
    "home_win":        "1 (Home)",
    "draw":            "X (Draw)",
    "away_win":        "2 (Away)",
    "dc_1x":           "1X",
    "dc_12":           "12",
    "dc_x2":           "X2",
}

PREFERRED_BOOKMAKERS = ["pinnacle", "bet365", "paddy-power", "betmgm-uk", "betfair-exchange"]

# ─── Modelo ─────────────────────────────────────────────────────────
POISSON_MAX_GOALS = 10
HOME_ADVANTAGE    = 0.12
DIXON_COLES_RHO   = -0.10
LEAGUE_AVG_GOALS  = 2.70

WEIGHT_POISSON    = 0.55
WEIGHT_MARKET     = 0.35
WEIGHT_FORM       = 0.10

# ─── Value & Kelly ──────────────────────────────────────────────────
MIN_EDGE          = 0.035
MIN_EV_PERCENT    = 4.0
KELLY_FRACTION    = 0.20
BANKROLL_UNITS    = 100
MAX_STAKE_UNITS   = 8.0

# ─── Scoring de contexto (soft filters) ─────────────────────────────
MIN_CONTEXT_SCORE = 45

BTTS_RATE_GOOD    = 0.55
XGA_SOFT_MIN      = 1.05
CLEAN_SHEET_SOFT_MAX = 0.40
REST_DAYS_IDEAL   = 4
REST_DAYS_MIN     = 2

# ─── Clasificación de oportunidades ─────────────────────────────────
LEVEL1_EDGE       = 0.07
LEVEL1_CONTEXT    = 65
LEVEL2_EDGE       = 0.04
LEVEL2_CONTEXT    = 50

# ─── Paralelismo y límites ──────────────────────────────────────────
MAX_WORKERS       = 12
MAX_MATCHES       = 250
RECENT_MATCHES_N  = 12
