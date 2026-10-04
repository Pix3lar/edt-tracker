"""Point d'entrée : python -m edt_bot [run|setup|demo] [--dry-run]

⚠️ Le dépôt GitHub est public : les journaux d'exécution le sont aussi.
Ce programme n'écrit donc JAMAIS le contenu de l'emploi du temps dans la
console — seulement des compteurs. Les détails partent uniquement sur Discord.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from .diff import ANNULE, MODIFIE, NOUVEAU, Change, compute_changes
from .discord_api import Discord, DiscordError
from .formatting import (dm_message, fmt_detection, log_baseline, log_message, log_no_change,
                         needs_pdf)
from .ics import FetchError, fetch_ics, parse_ics
from .priority import degree
from .report import build_report
from .state import State

FAILURE_ALERT_AFTER = 3        # DM après 3 échecs de suite (≈ 6 h)
SUSPICIOUS_RATIO = 0.5         # EDT soudain réduit de moitié → probablement une panne côté université
SUSPICIOUS_MAX_RUNS = 3


class Config:
    def __init__(self, dry_run: bool = False):
        self.ics_url = os.environ.get("ICS_URL", "").strip()
        self.token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
        self.user_id = os.environ.get("DISCORD_USER_ID", "").strip()
        self.log_channel = os.environ.get("DISCORD_LOG_CHANNEL_ID", "").strip()
        self.state_file = os.environ.get("STATE_FILE", "state/state.json")
        self.report_dir = os.environ.get("REPORT_DIR", "out")
        self.log_quiet_runs = os.environ.get("LOG_QUIET_RUNS", "true").lower() not in ("0", "false", "non", "no")
        self.dry_run = dry_run

    def check(self) -> list[str]:
        missing = [n for n, v in [("ICS_URL", self.ics_url), ("DISCORD_BOT_TOKEN", self.token),
                                  ("DISCORD_USER_ID", self.user_id),
                                  ("DISCORD_LOG_CHANNEL_ID", self.log_channel)] if not v]
        if self.dry_run:
            missing = [m for m in missing if m == "ICS_URL"]
        return missing


class Out:
    """Envoi vers Discord, ou vers la console en mode --dry-run (tests en local uniquement)."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.discord = None if cfg.dry_run else Discord(cfg.token)
        self.sent: list[tuple[str, str, list[str]]] = []

    def dm(self, text: str, files: list[str] | None = None) -> None:
        self.sent.append(("dm", text, files or []))
        if self.discord:
            self.discord.send_dm(self.cfg.user_id, text, files)
        else:
            print(f"--- DM ---\n{text}\n{files or ''}")

    def log(self, text: str) -> bool:
        """Les logs ne sont jamais bloquants : un échec ici n'empêche pas le reste."""
        self.sent.append(("log", text, []))
        if not self.discord:
            print(f"--- LOG ---\n{text}")
            return True
        try:
            self.discord.send(self.cfg.log_channel, text)
            return True
        except DiscordError as e:
            print(f"Salon de logs injoignable : {e}", file=sys.stderr)
            return False


def now_utc() -> datetime:
    forced = os.environ.get("EDT_NOW")  # utilisé par les tests
    if forced:
        return datetime.fromisoformat(forced).astimezone(timezone.utc)
    return datetime.now(timezone.utc)


def load_calendar(url: str) -> str:
    if os.path.exists(url):  # fichier local (tests)
        with open(url, encoding="utf-8") as f:
            return f.read()
    return fetch_ics(url)


# ---------------------------------------------------------------------------
def run(cfg: Config, out: Out | None = None) -> int:
    out = out or Out(cfg)
    now = now_utc()
    state = State.load(cfg.state_file)

    # 1. Télécharger l'emploi du temps
    try:
        new = parse_ics(load_calendar(cfg.ics_url))
        if not new:
            raise FetchError("calendrier vide")
    except Exception as e:  # noqa: BLE001 — toute erreur de récupération est gérée pareil
        reason = str(e) if isinstance(e, FetchError) else f"{type(e).__name__}"
        state.failures += 1
        print(f"Téléchargement de l'EDT impossible ({reason}) — échec n°{state.failures}")
        out.log(f"⚠️ {fmt_detection(now)} — Impossible de récupérer l'emploi du temps ({reason}). "
                f"État conservé, nouvel essai à la prochaine exécution ({state.failures} échec(s) de suite).")
        if state.failures >= FAILURE_ALERT_AFTER and not state.failure_alert_sent:
            try:
                out.dm(f"⚠️ Le suivi de l'emploi du temps échoue depuis {state.failures} exécutions ({reason}). "
                       "Je te préviens dès que ça refonctionne.")
                state.failure_alert_sent = True
            except DiscordError as e:
                print(f"Envoi du DM d'alerte impossible : {e}", file=sys.stderr)
        state.save(cfg.state_file)
        return 0

    # 2. Garde-fou : EDT soudain presque vide (souvent une panne côté Hyperplanning)
    old = state.courses
    if old and len(old) >= 20 and len(new) < SUSPICIOUS_RATIO * len(old):
        state.suspicious_runs += 1
        if state.suspicious_runs < SUSPICIOUS_MAX_RUNS:
            print(f"EDT suspect : {len(new)} cours contre {len(old)} — ignoré pour cette fois")
            out.log(f"⚠️ {fmt_detection(now)} — L'EDT téléchargé ne contient que {len(new)} cours "
                    f"(contre {len(old)}). Probable souci côté université : ignoré pour l'instant.")
            state.save(cfg.state_file)
            return 0
        out.log(f"ℹ️ {fmt_detection(now)} — L'EDT réduit ({len(new)} cours) persiste : je l'accepte comme nouvelle référence.")
        print("EDT réduit accepté comme nouvelle référence")
        state.courses, state.suspicious_runs = new, 0
        state.updated_at = now.isoformat()
        state.save(cfg.state_file)
        return 0
    state.suspicious_runs = 0

    if state.failure_alert_sent:
        try:
            out.dm("✅ Le suivi de l'emploi du temps refonctionne.")
        except DiscordError as e:
            print(f"Envoi du DM impossible : {e}", file=sys.stderr)
    state.failures, state.failure_alert_sent = 0, False

    # 3. Première exécution : simple prise de référence, aucune alerte
    if old is None:
        print(f"Première exécution : {len(new)} cours enregistrés comme référence")
        out.log(log_baseline(now, len(new)))
        state.courses, state.updated_at = new, now.isoformat()
        state.save(cfg.state_file)
        return 0

    # 4. Comparer
    changes = compute_changes(old, new, now)
    if not changes:
        print(f"Aucun changement ({len(new)} cours suivis)")
        if cfg.log_quiet_runs:
            out.log(log_no_change(now, len(new)))
        state.courses, state.updated_at = new, now.isoformat()
        state.save(cfg.state_file)
        return 0

    pdf_path = build_report(changes, now, cfg.report_dir) if needs_pdf(changes) else None
    print(f"{len(changes)} changement(s) détecté(s) — PDF : {'oui' if pdf_path else 'non'}")

    # 5. DM d'abord. S'il échoue, on ne met PAS l'état à jour → ce sera renvoyé au prochain passage.
    try:
        out.dm(dm_message(changes, now, pdf_sent=bool(pdf_path)), [pdf_path] if pdf_path else None)
    except DiscordError as e:
        print(f"Envoi du DM impossible : {e}", file=sys.stderr)
        out.log(log_message(changes, now, bool(pdf_path), dm_ok=False) + f"\n⚠️ DM en échec : {e}")
        state.failures += 1
        state.save(cfg.state_file)
        return 1

    out.log(log_message(changes, now, bool(pdf_path), dm_ok=True))
    state.courses, state.updated_at = new, now.isoformat()
    state.save(cfg.state_file)
    return 0


# ---------------------------------------------------------------------------
def setup(cfg: Config) -> int:
    """Vérifie toute la configuration et envoie un message de test (à lancer une fois)."""
    ok = True
    d = Discord(cfg.token)
    try:
        name = d.identify_once()
        print(f"✅ Bot connecté à Discord ({name})")
    except Exception as e:  # noqa: BLE001
        print(f"❌ Connexion du bot impossible : {e} — vérifie DISCORD_BOT_TOKEN")
        return 1
    try:
        d.send_dm(cfg.user_id, "👋 Test : le bot de suivi d'emploi du temps peut t'écrire en DM. Tout est prêt !")
        print("✅ DM de test envoyé")
    except DiscordError as e:
        ok = False
        print(f"❌ DM impossible : {e} — vérifie DISCORD_USER_ID, que le bot est sur un serveur avec toi "
              "et que tu acceptes les messages privés des membres de ce serveur")
    try:
        d.send(cfg.log_channel, "🧪 Test : le salon de logs fonctionne.")
        print("✅ Message de test envoyé dans le salon de logs")
    except DiscordError as e:
        ok = False
        print(f"❌ Salon de logs injoignable : {e} — vérifie DISCORD_LOG_CHANNEL_ID et les permissions du bot")
    try:
        courses = parse_ics(load_calendar(cfg.ics_url))
        print(f"✅ Emploi du temps récupéré : {len(courses)} événements")
        if not courses:
            ok = False
    except Exception as e:  # noqa: BLE001
        ok = False
        print(f"❌ Emploi du temps illisible : {e} — vérifie ICS_URL")
    return 0 if ok else 1


def demo(cfg: Config, out: Out | None = None) -> int:
    """Envoie un exemple de notification + PDF fabriqué à partir de ton vrai EDT (rien n'est modifié)."""
    out = out or Out(cfg)
    now = now_utc()
    courses = sorted((c for c in parse_ics(load_calendar(cfg.ics_url)).values()
                      if c.end_dt > now and not c.is_status_marker), key=lambda c: c.start)
    if len(courses) < 3:
        print("Pas assez de cours à venir pour fabriquer une démo")
        return 1
    fake: list[Change] = []
    for i, c in enumerate(courses[:8]):
        if i % 3 == 0:
            fake.append(Change(ANNULE, replace(c, statut="Annulation"), c))
        elif i % 3 == 1:
            fake.append(Change(MODIFIE, replace(c, salle="Salle H2"), c, ["salle"]))
        else:
            moved = replace(c, start=(c.start_dt + timedelta(hours=2)).isoformat(),
                            end=(c.end_dt + timedelta(hours=2)).isoformat())
            fake.append(Change(MODIFIE, moved, c, ["horaire"]))
    if len(courses) > 8:
        fake.append(Change(NOUVEAU, courses[-1]))
    from .diff import local, relevant_start
    for ch in fake:
        ch.ref_start = relevant_start(ch, now)
        ch.degree = degree(local(ch.ref_start).date(), local(now).date())
    fake.sort(key=Change.sort_key)
    pdf = build_report(fake, now, cfg.report_dir)
    out.dm("🧪 **DÉMO — ces changements sont fictifs**\n\n" + dm_message(fake, now, pdf_sent=True), [pdf])
    out.log("🧪 DÉMO (changements fictifs)\n" + log_message(fake, now, True, dm_ok=True))
    print(f"Démo envoyée ({len(fake)} changements fictifs)")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="edt_bot", description="Suivi des changements d'emploi du temps")
    p.add_argument("mode", nargs="?", default="run", choices=["run", "setup", "demo"])
    p.add_argument("--dry-run", action="store_true", help="affiche les messages au lieu de les envoyer (local)")
    args = p.parse_args(argv)
    cfg = Config(dry_run=args.dry_run)
    missing = cfg.check()
    if missing:
        print("Secrets manquants : " + ", ".join(missing))
        return 2
    if args.mode == "setup":
        return setup(cfg)
    if args.mode == "demo":
        return demo(cfg)
    try:
        return run(cfg)
    except DiscordError as e:
        print(f"Erreur Discord : {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
