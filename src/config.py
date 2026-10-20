"""
Módulo de Configuración Central y Gobernanza de Parámetros Cuantitativos.
Valida rigor matemático, tipado estricto e inmutabilidad para sistemas de value betting.
"""
from __future__ import annotations

import os
import math
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Final, Mapping

from dotenv import load_dotenv

# Carga de variables de entorno desde .env si existe
load_dotenv()


class ConfigurationError(ValueError):
    """Excepción lanzada cuando los parámetros cuantitativos o de conexión violan restricciones de dominio."""
    pass


@dataclass(frozen=True)
class APIConfig:
    api_key: str
    base_url: str = "https://api.thestatsapi.com/api"
    timeout: int = 18
    per_page: int = 100
    max_retries: int = 4
    backoff_factor: float = 0.5

    def __post_init__(self) -> None:
        if not self.base_url.startswith(("http://", "https://")):
            raise ConfigurationError(f"BASE_URL inválida: {self.base_url}")
        if self.timeout <= 0:
            raise ConfigurationError("TIMEOUT debe ser estrictamente positivo.")
        if self.max_retries < 0:
            raise ConfigurationError("MAX_RETRIES no puede ser negativo.")
        if self.per_page <= 0 or self.per_page > 500:
            raise ConfigurationError("PER_PAGE debe estar en el rango (0, 500].")


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str
    chat_id: str

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token.strip() and self.chat_id.strip())


@dataclass(frozen=True)
class QuantitativeModelConfig:
    poisson_max_goals: int = 10
    home_advantage_factor: float = 1.12
    dixon_coles_rho: float = -0.05
    default_league_avg_goals: float = 2.70
    weight_model: float = 0.40
    weight_market: float = 0.60

    def __post_init__(self) -> None:
        if self.poisson_max_goals < 5:
            raise ConfigurationError("POISSON_MAX_GOALS insuficiente para convergencia de distribución.")
        if self.home_advantage_factor <= 0:
            raise ConfigurationError("HOME_ADVANTAGE_FACTOR debe ser estrictamente positivo.")
        if not -0.5 <= self.dixon_coles_rho <= 0.5:
            raise ConfigurationError("DIXON_COLES_RHO fuera de rango admisible (-0.5 a 0.5).")
        if self.default_league_avg_goals <= 0:
            raise ConfigurationError("DEFAULT_LEAGUE_AVG_GOALS debe ser positivo.")
        
        total_weight = self.weight_model + self.weight_market
        if not math.isclose(total_weight, 1.0, rel_tol=1e-5):
            raise ConfigurationError(
                f"Pesos de ensamble no normalizados: modelo ({self.weight_model}) + "
                f"mercado ({self.weight_market}) = {total_weight:.4f} != 1.0"
            )


@dataclass(frozen=True)
class RiskAndFilterConfig:
    min_edge: float = 0.030
    min_ev_percent: float = 3.5
    kelly_fraction: float = 0.06
    bankroll_units: float = 100.0
    max_stake_units: float = 1.5
    level1_edge: float = 0.065
    level1_context: float = 68.0
    level2_edge: float = 0.030
    level2_context: float = 55.0
    min_context_score: float = 48.0

    def __post_init__(self) -> None:
        if self.min_edge < 0:
            raise ConfigurationError("MIN_EDGE debe ser no negativo.")
        if not (0 < self.kelly_fraction <= 0.5):
            raise ConfigurationError("KELLY_FRACTION prudencial debe residir en (0, 0.5].")
        if self.bankroll_units <= 0:
            raise ConfigurationError("BANKROLL_UNITS debe ser estrictamente positivo.")
        if not (0 < self.max_stake_units <= self.bankroll_units):
            raise ConfigurationError("MAX_STAKE_UNITS inválido respecto a BANKROLL_UNITS.")
        if self.level1_edge < self.level2_edge:
            raise ConfigurationError("Inconsistencia en jerarquía de convicción: LEVEL1_EDGE < LEVEL2_EDGE.")


@dataclass(frozen=True)
class DataAndConcurrencyConfig:
    max_workers: int = 6
    max_matches: int = 200
    recent_matches_n: int = 12
    min_matches_for_rating: int = 4
    save_picks_json: bool = True
    picks_dir: Path = field(default_factory=lambda: Path("picks"))

    def __post_init__(self) -> None:
        if self.max_workers <= 0:
            raise ConfigurationError("MAX_WORKERS debe ser positivo.")
        if self.min_matches_for_rating < 1:
            raise ConfigurationError("MIN_MATCHES_FOR_RATING debe ser al menos 1.")
        if self.save_picks_json:
            self.picks_dir.mkdir(parents=True, exist_ok=True)


# =====================================================================
# INSTANCIACIÓN DE CONFIGURACIONES VALIDADAS
# =====================================================================

_API_KEY_ENV: Final[str] = os.getenv("THESTATSAPI_API_KEY", "").strip()
_TG_TOKEN_ENV: Final[str] = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
_TG_CHAT_ENV: Final[str] = os.getenv("TELEGRAM_CHAT_ID", "").strip()

api_config = APIConfig(api_key=_API_KEY_ENV)
telegram_config = TelegramConfig(bot_token=_TG_TOKEN_ENV, chat_id=_TG_CHAT_ENV)
model_config = QuantitativeModelConfig()
risk_config = RiskAndFilterConfig()
runtime_config = DataAndConcurrencyConfig()

# =====================================================================
# CONSTANTES DE COMPATIBILIDAD GLOBAL (INTERFAZ PÚBLICA INMUTABLE)
# =====================================================================

API_KEY: Final[str] = api_config.api_key
BASE_URL: Final[str] = api_config.base_url
TIMEOUT: Final[int] = api_config.timeout
PER_PAGE: Final[int] = api_config.per_page
MAX_RETRIES: Final[int] = api_config.max_retries
BACKOFF_FACTOR: Final[float] = api_config.backoff_factor

TELEGRAM_TOKEN: Final[str] = telegram_config.bot_token
TELEGRAM_CHAT: Final[str] = telegram_config.chat_id
TELEGRAM_CONFIGURED: Final[bool] = telegram_config.is_configured

# Competiciones
TOP_COMPETITION_IDS: Final[tuple[str, ...]] = (
    "comp_3039",   # Premier League
    "comp_8814",   # LaLiga
    "comp_5840",   # Serie A
    "comp_3850",   # Bundesliga
    "comp_5099",   # Ligue 1
    "comp_1642",   # Champions League
    "comp_1880",   # Europa League
)

COMPETITION_IDS: Final[tuple[str, ...]] = ()

ACTIVE_COMPETITIONS: Final[frozenset[str]] = frozenset(
    COMPETITION_IDS if COMPETITION_IDS else TOP_COMPETITION_IDS
)

# Filtro de nombres para categorías inferiores y juveniles
YOUTH_KEYWORDS: Final[tuple[str, ...]] = (
    "jong ", "u19", "u-19", "u21", "u-21", "u23", "u-23",
    "youth", "junior", "juvenil", "reserve", "reserves",
    " ii", " iii", " b ", " b)", "(b)", "amateurs",
    "academy", "under 19", "under 21", "under 23",
)

# Mercados normalizados
_RAW_MARKETS: dict[str, str] = {
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
MARKETS: Final[Mapping[str, str]] = MappingProxyType(_RAW_MARKETS)

# Sharp Bookmakers (Peso bayesiano superior para fijación de precio de mercado)
SHARP_BOOKMAKERS: Final[frozenset[str]] = frozenset({
    "pinnacle",
    "betfair-exchange",
    "betfair",
    "sbobet",
    "matchbook",
})

# Parámetros Modelo Estadístico
POISSON_MAX_GOALS: Final[int] = model_config.poisson_max_goals
HOME_ADVANTAGE_FACTOR: Final[float] = model_config.home_advantage_factor
DIXON_COLES_RHO: Final[float] = model_config.dixon_coles_rho
DEFAULT_LEAGUE_AVG_GOALS: Final[float] = model_config.default_league_avg_goals
WEIGHT_MODEL: Final[float] = model_config.weight_model
WEIGHT_MARKET: Final[float] = model_config.weight_market

# Riesgo y Kelly
MIN_EDGE: Final[float] = risk_config.min_edge
MIN_EV_PERCENT: Final[float] = risk_config.min_ev_percent
KELLY_FRACTION: Final[float] = risk_config.kelly_fraction
BANKROLL_UNITS: Final[float] = risk_config.bankroll_units
MAX_STAKE_UNITS: Final[float] = risk_config.max_stake_units

# Jerarquización de Convicción
LEVEL1_EDGE: Final[float] = risk_config.level1_edge
LEVEL1_CONTEXT: Final[float] = risk_config.level1_context
LEVEL2_EDGE: Final[float] = risk_config.level2_edge
LEVEL2_CONTEXT: Final[float] = risk_config.level2_context
MIN_CONTEXT_SCORE: Final[float] = risk_config.min_context_score

# Ejecución y Datos
MAX_WORKERS: Final[int] = runtime_config.max_workers
MAX_MATCHES: Final[int] = runtime_config.max_matches
RECENT_MATCHES_N: Final[int] = runtime_config.recent_matches_n
MIN_MATCHES_FOR_RATING: Final[int] = runtime_config.min_matches_for_rating
SAVE_PICKS_JSON: Final[bool] = runtime_config.save_picks_json
PICKS_DIR: Final[Path] = runtime_config.picks_dir