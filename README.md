# Football Betting Analyzer v2 — Value Finder

Sistema para encontrar **verdaderas oportunidades de value betting** usando TheStatsAPI.

## Qué incluye

- Multi-mercado: BTTS Yes/No, Over/Under 2.5, 1X2, DNB, Double Chance
- Modelo Poisson + Dixon-Coles con matriz de scores completa
- Mejor cuota entre bookmakers (maximiza edge real)
- Soft scoring contextual (0-100) en lugar de filtros binarios rígidos
- Lesiones/suspensiones vía endpoint oficial
- Kelly fraccional + clasificación L1 / L2
- Pre-match y Live
- Envío a Telegram con acumulador sugerido

## Instalación

```bash
pip install -r requirements.txt
export THESTATSAPI_API_KEY="tu_key"
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."
