"""
Orquestador en vivo: analiza partidos EN CURSO con cuotas live.
Se ejecuta cada 30 min.
"""
import logging
from datetime import date

from src.config import COMPETITION_IDS, MAX_MATCHES
from src.api_client import matches, match_stats, match_odds_live
from src.analyzer import analyze
from src.telegram_bot import send

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def main():
    today = date.today().isoformat()
    log.info("═══ Análisis en vivo %s ═══", today)

    comp_filter = COMPETITION_IDS[0] if COMPETITION_IDS else None
    live_matches = matches(
        date_from=today,
        date_to=today,
        status="live",
        competition_id=comp_filter,
    )
    log.info("Partidos en vivo: %d", len(live_matches))

    eligible = [m for m in live_matches if m.get("live_odds_available")]
    log.info("Con cuotas live: %d", len(eligible))

    all_bets: list[str] = []
    total_analyzed = 0

    for m in eligible[:MAX_MATCHES]:
        mid = m.get("id")
        if not mid:
            continue
        try:
            st = match_stats(mid) if m.get("xg_available") else {}
            od = match_odds_live(mid)
            bets = analyze(match=m, st=st, od=od)
            all_bets.extend(bets)
            total_analyzed += 1
        except Exception as e:
            log.warning("  ⚠ %s: %s", mid, e)

    log.info("Analizados: %d | Apuestas: %d", total_analyzed, len(all_bets))

    if all_bets:
        header = (
            f"🔴 <b>OPORTUNIDADES EN VIVO — {today}</b>\n"
            f"📊 {total_analyzed} partidos en curso\n\n"
        )
        body = "\n".join(all_bets[:20])
        msg = header + body
        if len(msg) > 4000:
            msg = header + body[:3900] + "\n…(truncado)"
        send(msg)
    else:
        log.info("Sin oportunidades en vivo. No se envía mensaje.")


if __name__ == "__main__":
    main()   
