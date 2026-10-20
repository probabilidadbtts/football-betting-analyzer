"""
Pre-match: solo ligas reconocidas + sin juveniles/U21/reservas.
Predicción con xG de últimos 5 home del local y 5 away del visitante.
Integrado con Kivy para compatibilidad gráfica con Android / Buildozer.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# --- Importaciones de Kivy (Necesarias para la interfaz gráfica de Android) ---
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock

# --- Importaciones del proyecto ---
from src.config import (
    COMPETITION_IDS, TOP_COMPETITION_IDS, MAX_MATCHES, MAX_WORKERS,
    SAVE_PICKS_JSON, PICKS_DIR, YOUTH_KEYWORDS,
)
from src.api_client import (
    matches, match_odds,
    team_home_matches, team_away_matches,
    team_injuries_suspensions, team_squad,
    team_id_from_match, team_name_from_match,
)
from src.analyzer import analyze_match
from src.telegram_bot import send_report

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def _is_youth_team(name: str) -> bool:
    if not name:
        return False
    lower = f" {name.lower()} "
    return any(kw in lower for kw in YOUTH_KEYWORDS)


def _get_competitions() -> list[str]:
    if COMPETITION_IDS:
        return COMPETITION_IDS
    return TOP_COMPETITION_IDS


def _process_single(m: dict) -> dict | None:
    mid = m.get("id")
    if not mid:
        return None

    home = team_name_from_match(m, "home")
    away = team_name_from_match(m, "away")

    # Descartar juveniles / U21 / reservas
    if _is_youth_team(home) or _is_youth_team(away):
        log.debug("Descartado (juvenil): %s vs %s", home, away)
        return None

    try:
        od = match_odds(mid)
        if not od or not od.get("bookmakers"):
            return None

        hid = team_id_from_match(m, "home")
        aid = team_id_from_match(m, "away")

        h_home = team_home_matches(hid, n=5)
        a_away = team_away_matches(aid, n=5)

        h_inj = team_injuries_suspensions(hid, current=True)
        a_inj = team_injuries_suspensions(aid, current=True)
        h_squad = team_squad(hid)
        a_squad = team_squad(aid)

        h2h = [
            rm for rm in h_home
            if team_id_from_match(rm, "home") == aid or team_id_from_match(rm, "away") == aid
        ]

        return analyze_match(
            match=m,
            odds_payload=od,
            home_home_matches=h_home,
            away_away_matches=a_away,
            home_injuries=h_inj,
            away_injuries=a_inj,
            home_squad=h_squad,
            away_squad=a_squad,
            h2h_matches=h2h,
            is_live=False,
        )
    except Exception as e:
        log.warning("Error %s: %s", mid, e)
        return None


def run_analysis(log_callback=None):
    """Ejecuta la lógica de análisis pasando logs a la interfaz si están disponibles."""
    def log_msg(msg: str):
        log.info(msg)
        if log_callback:
            log_callback(msg)

    today = date.today().isoformat()
    log_msg(f"Pre-Match (ligas reconocidas, sin juveniles) — {today}")

    comps = _get_competitions()
    pool: list[dict] = []

    if comps:
        for cid in comps:
            pool.extend(
                matches(date_from=today, date_to=today, status="scheduled", competition_id=cid)
            )
        log_msg(f"Competiciones filtradas: {len(comps)}")
    else:
        pool = matches(date_from=today, date_to=today, status="scheduled")
        log_msg("Sin filtro de competición (todas las ligas), se eliminarán juveniles")

    seen, unique = set(), []
    for m in pool:
        mid = m.get("id")
        if mid and mid not in seen:
            seen.add(mid)
            unique.append(m)

    eligible = [m for m in unique if m.get("odds_available")]
    log_msg(f"Partidos con cuotas (antes de filtrar juveniles): {len(eligible)}")

    candidates = eligible[:MAX_MATCHES]
    results, value_matches = [], []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as exe:
        futs = {exe.submit(_process_single, m): m for m in candidates}
        for fut in as_completed(futs):
            res = fut.result()
            if res:
                results.append(res)
                if res.get("has_value"):
                    value_matches.append(res)
                    log_msg(
                        f"✓ {res.get('home')} vs {res.get('away')} | "
                        f"xG H:{res.get('home_xg_matches')} A:{res.get('away_xg_matches')} | "
                        f"picks:{len(res.get('value_picks') or [])}"
                    )

    log_msg(f"Analizados: {len(results)} | Con valor: {len(value_matches)}")

    if SAVE_PICKS_JSON:
        Path(PICKS_DIR).mkdir(parents=True, exist_ok=True)
        with open(f"{PICKS_DIR}/prematch_{today}.json", "w", encoding="utf-8") as f:
            json.dump({"title": f"PRE-MATCH {today}", "matches": results}, f, ensure_ascii=False, indent=2, default=str)

    send_report(value_matches, f"PRE-MATCH {today}", len(results))
    log_msg("¡Análisis completado exitosamente!")


# --- Interfaz Gráfica con Kivy (Android App Wrapper) ---
class MainApp(App):
    def build(self):
        self.title = "Football Betting Analyzer"
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        self.log_label = Label(
            text="Iniciando analizador de fútbol...\n", 
            size_hint_y=None, 
            halign='left', 
            valign='top'
        )
        self.log_label.bind(texture_size=self.log_label.setter('size'))

        scroll = ScrollView()
        scroll.add_widget(self.log_label)
        layout.add_widget(scroll)

        return layout

    def on_start(self):
        # Inicia el hilo secundario para evitar que la app se bloquee
        threading.Thread(target=self._background_worker, daemon=True).start()

    def update_log(self, text: str):
        # Actualiza el texto en la interfaz desde el hilo principal
        Clock.schedule_once(lambda dt: self._append_log(text))

    def _append_log(self, text: str):
        self.log_label.text += f"\n{text}"

    def _background_worker(self):
        try:
            run_analysis(log_callback=self.update_log)
        except Exception as e:
            self.update_log(f"Error grave en ejecución: {e}")


if __name__ == "__main__":
    MainApp().run()
