"""
Configuración central del analizador cuantitativo de value betting.
Solo ligas reconocidas + sin juveniles/U21. Predicción basada en xG real.
"""
from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()

# --- TheStatsAPI ---
API_KEY: str = os.getenv("THESTATSAPI_API_KEY", "")
BASE_URL: str = "https://api.thestatsapi.com/api"
TIMEOUT: int = 18
PER_PAGE: int = 100
MAX_RETRIES: int = 4

# --- Telegram ---
TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT: str = os.getenv("TELEGRAM_CHAT_ID", "")

# --- Competiciones reconocidas ---
# Si COMPETITION_IDS está vacío se usan TOP_COMPETITION_IDS.
# Rellena más IDs con: GET /football/competitions?search=Bundesliga
TOP_COMPETITION_IDS: list[str] = [
    "comp_3039",   # Premier League
    "comp_8814",   # LaLiga
    "comp_5840",   # Serie A
    # Añade aquí más ligas reconocidas:
    # "comp_XXXX", # Bundesliga
    # "comp_XXXX", # Ligue 1
    # "comp_XXXX", # Eredivisie
    # "comp_XXXX", # Championship
    # "comp_XXXX", # Segunda División
    # "comp_XXXX", # Serie B
    # "comp_XXXX", # 2. Bundesliga
    # "comp_XXXX", # Champions League
    # "comp_XXXX", # Europa League
]

# Vacío = usa TOP_COMPETITION_IDS. Si tiene valores, solo analiza esas.
COMPETITION_IDS: list[str] = []

# Palabras que identifican juveniles / reservas / U21 (se descartan)
YOUTH_KEYWORDS: list[str] = [
    "jong ", "u19", "u-19", "u21", "u-21", "u23", "u-23",
    "youth", "junior", "juvenil", "reserve", "reserves",
    " ii", " iii", " b ", " b)", "(b)", "amateurs",
    "academy", "under 19", "under 21", "under 23",
]

# --- Mercados Analizados ---
MARKETS = {
    "home_win": "1 (Home)",
    "draw": "X (Draw)",
    "away_win": "2 (Away)",
    "over_25": "Over 2.5",
    "under_25": "Under 2.5",
    "btts_yes": "BTTS Yes",
    "btts_no": "BTTS No",
    "dc_1x": "1X",
    "dc_x2": "X2",
    "dc_12": "12",
    "home_dnb": "DNB 1",
    "away_dnb": "DNB 2",
}

# Bookmakers sharp (peso extra al calcular fair probability)
SHARP_BOOKMAKERS = ["pinnacle", "betfair-exchange", "betfair", "sbobet", "matchbook"]

# --- Parámetros del Modelo Matemático ---
POISSON_MAX_GOALS: int = 10
HOME_ADVANTAGE_FACTOR: float = 1.12
DIXON_COLES_RHO: float = -0.05
DEFAULT_LEAGUE_AVG_GOALS: float = 2.70

# Pesos del ensamble (Modelo vs Mercado desmargenado)
WEIGHT_MODEL: float = 0.40
WEIGHT_MARKET: float = 0.60

# --- Filtros de Valor y Kelly ---
MIN_EDGE: float = 0.030
MIN_EV_PERCENT: float = 3.5
KELLY_FRACTION: float = 0.06
BANKROLL_UNITS: float = 100.0
MAX_STAKE_UNITS: float = 1.5

# --- Niveles de Convicción ---
LEVEL1_EDGE: float = 0.065
LEVEL1_CONTEXT: float = 68.0
LEVEL2_EDGE: float = 0.030
LEVEL2_CONTEXT: float = 55.0
MIN_CONTEXT_SCORE: float = 48.0

# --- Concurrencia y Datos ---
MAX_WORKERS: int = 6
MAX_MATCHES: int = 200
RECENT_MATCHES_N: int = 12
MIN_MATCHES_FOR_RATING: int = 4          # Mínimo de partidos con xG real por lado

# Guardar picks para análisis posterior
SAVE_PICKS_JSON: bool = True
PICKS_DIR: str = "picks"
