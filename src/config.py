"""
Configuración central del analizador cuantitativo de value betting.
"""
from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()

# --- TheStatsAPI ---
API_KEY: str = os.getenv("THESTATSAPI_API_KEY", "")
BASE_URL: str = "https://api.thestatsapi.com/api"
TIMEOUT: int = 15
PER_PAGE: int = 100
MAX_RETRIES: int = 3

# --- Telegram ---
TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT: str = os.getenv("TELEGRAM_CHAT_ID", "")

# Competiciones (vacío = todas las que tengan cuotas)
COMPETITION_IDS: list[str] = []

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

SHARP_BOOKMAKERS = ["pinnacle", "betfair-exchange", "betfair"]

# --- Parámetros del Modelo Matemático ---
POISSON_MAX_GOALS: int = 9
HOME_ADVANTAGE_FACTOR: float = 1.10   # +10% de ventaja ofensiva local promedio
DIXON_COLES_RHO: float = -0.06        # Correlación empírica para bajas puntuaciones (0-0, 1-0, 0-1, 1-1)
DEFAULT_LEAGUE_AVG_GOALS: float = 2.65

# Pesos del ensamble Bayesiano (Modelo vs Mercado desmargenado)
WEIGHT_MODEL: float = 0.45
WEIGHT_MARKET: float = 0.55

# --- Filtros de Valor y Kelly Criterion ---
MIN_EDGE: float = 0.025               # Mínimo 2.5% de ventaja real
MIN_EV_PERCENT: float = 3.0           # Mínimo +3.0% de Valor Esperado
KELLY_FRACTION: float = 0.08          # Criterio de Kelly fraccional conservador (1/12 Kelly)
BANKROLL_UNITS: float = 100.0
MAX_STAKE_UNITS: float = 2.0          # Máximo 2% del bankroll por selección

# --- Niveles de Convicción ---
LEVEL1_EDGE: float = 0.055
LEVEL1_CONTEXT: float = 62.0
LEVEL2_EDGE: float = 0.025
LEVEL2_CONTEXT: float = 48.0
MIN_CONTEXT_SCORE: float = 40.0

# --- Concurrencia y Datos ---
MAX_WORKERS: int = 8
MAX_MATCHES: int = 150
RECENT_MATCHES_N: int = 15
