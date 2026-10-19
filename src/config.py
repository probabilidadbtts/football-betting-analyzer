"""
Configuración central del analizador cuantitativo de value betting.
Enfocado en fiabilidad (pocos falsos positivos) y protección de bankroll.
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

# Competiciones
# Vacío = analizar TODAS las ligas del día (recomendado para cobertura máxima)
# Si rellenas COMPETITION_IDS, solo se analizan esas.
# TOP_COMPETITION_IDS queda como lista de referencia opcional.
TOP_COMPETITION_IDS: list[str] = [
    "comp_3039",   # Premier League (ENG)
    "comp_8814",   # LaLiga
    "comp_5840",   # Serie A
]

# Vacío = TODAS las ligas. Rellena solo si quieres filtrar.
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

# Bookmakers sharp (peso extra al calcular fair probability)
SHARP_BOOKMAKERS = ["pinnacle", "betfair-exchange", "betfair", "sbobet", "matchbook"]

# --- Parámetros del Modelo Matemático ---
POISSON_MAX_GOALS: int = 10
HOME_ADVANTAGE_FACTOR: float = 1.12          # +12% ventaja ofensiva local (ligeramente más realista)
DIXON_COLES_RHO: float = -0.05              # Correlación empírica baja-puntuación
DEFAULT_LEAGUE_AVG_GOALS: float = 2.70

# Pesos del ensamble (Modelo vs Mercado desmargenado)
# Más peso al mercado = más conservador (menos overfit del modelo)
WEIGHT_MODEL: float = 0.40
WEIGHT_MARKET: float = 0.60

# --- Filtros de Valor y Kelly (más estrictos = más fiables) ---
MIN_EDGE: float = 0.030                     # Mínimo 3.0% edge real
MIN_EV_PERCENT: float = 3.5                 # Mínimo +3.5% EV
KELLY_FRACTION: float = 0.06                # ~1/16 Kelly (muy conservador)
BANKROLL_UNITS: float = 100.0
MAX_STAKE_UNITS: float = 1.5                # Máximo 1.5% del bankroll por pick

# --- Niveles de Convicción (más exigentes) ---
LEVEL1_EDGE: float = 0.065
LEVEL1_CONTEXT: float = 68.0
LEVEL2_EDGE: float = 0.030
LEVEL2_CONTEXT: float = 55.0
MIN_CONTEXT_SCORE: float = 48.0

# --- Concurrencia y Datos ---
MAX_WORKERS: int = 6
MAX_MATCHES: int = 200                      # Tope de partidos a intentar analizar
RECENT_MATCHES_N: int = 12
MIN_MATCHES_FOR_RATING: int = 5

# Parar el workflow cuando se encuentren N partidos con valor
TARGET_VALUE_MATCHES: int = 20

# Guardar picks para análisis posterior
SAVE_PICKS_JSON: bool = True
PICKS_DIR: str = "picks"
