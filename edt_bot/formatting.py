"""Mise en forme des messages (français, heure de Martinique)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from .diff import (ANNULATION_LEVEE, ANNULE, MODIFIE, NOUVEAU, REPORTE, SUPPRIME,
                   Change, local)
from .ics import Course
from .priority import EMOJIS, IMPORTANT, LABELS, MOYEN, URGENT

JOURS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
KIND_EMOJI = {NOUVEAU: "🆕", MODIFIE: "✏️", ANNULE: "❌", REPORTE: "⏳", SUPPRIME: "🗑️", ANNULATION_LEVEE: "↩️"}
DEGREE_HINT = {URGENT: "cette semaine", IMPORTANT: "les 2 semaines suivantes",
               MOYEN: "plus tard ce mois-ci", "D": "plus tard"}


def fmt_day(dt: datetime) -> str:
    d = local(dt)
    return f"{JOURS[d.weekday()]} {d:%d/%m}"


def fmt_time(dt: datetime) -> str:
    return f"{local(dt):%Hh%M}"


def fmt_slot(c: Course) -> str:
    return f"{fmt_day(c.start_dt)} · {fmt_time(c.start_dt)}–{fmt_time(c.end_dt)}"


def fmt_detection(now: datetime) -> str:
    return f"{fmt_day(now)} à {fmt_time(now)}"


def dash(v: str) -> str:
    return v if v else "—"


def detail(ch: Change) -> str:
    """Ce qui a changé, en clair (ex. « salle : H2 → i4 »)."""
    o, n = ch.old, ch.course
    if ch.kind != MODIFIE or o is None:
        if ch.kind == REPORTE:
            return "reporté à une date ultérieure"
        return ""
    parts = []
    if "horaire" in ch.changed:
        if local(o.start_dt).date() == local(n.start_dt).date():
            parts.append(f"horaire : {fmt_time(o.start_dt)}–{fmt_time(o.end_dt)} → {fmt_time(n.start_dt)}–{fmt_time(n.end_dt)}")
        else:
            parts.append(f"déplacé : {fmt_day(o.start_dt)} {fmt_time(o.start_dt)} → {fmt_day(n.start_dt)} {fmt_time(n.start_dt)}")
    if "salle" in ch.changed:
        parts.append(f"salle : {dash(o.salle)} → {dash(n.salle)}")
    if "enseignant" in ch.changed:
        parts.append(f"enseignant : {dash(o.enseignant)} → {dash(n.enseignant)}")
    if "matière" in ch.changed:
        parts.append("matière modifiée")
    if "type" in ch.changed:
        parts.append(f"type : {dash(o.type)} → {dash(n.type)}")
    return ", ".join(parts)


def shown(ch: Change) -> Course:
    """Cours à afficher : pour une annulation, on garde la salle du cours d'origine."""
    c = ch.course
    if ch.kind in (ANNULE, REPORTE) and ch.old is not None and not c.salle and ch.old.salle:
        c = replace(c, salle=ch.old.salle)
    return c


def subject(c: Course) -> str:
    return f"{c.matiere} ({c.type})" if c.type else c.matiere


def needs_pdf(changes: list[Change], threshold: int = 5) -> bool:
    """PDF si plus de 5 changements urgents/importants, sauf si ce ne sont que des changements de salle."""
    ab = sum(1 for c in changes if c.degree in (URGENT, IMPORTANT))
    return ab > threshold and not all_room_only(changes)


def all_room_only(changes: list[Change]) -> bool:
    return bool(changes) and all(c.room_only for c in changes)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'s' if n > 1 else ''}"


def dm_message(changes: list[Change], now: datetime, pdf_sent: bool) -> str:
    """Notification concise envoyée en DM (triée par degré puis par date réelle)."""
    lines = [f"📅 **Emploi du temps — {_plural(len(changes), 'changement')}**",
             f"🕐 Détecté {fmt_detection(now)}"]
    current = None
    for ch in sorted(changes, key=Change.sort_key):
        if ch.degree != current:
            current = ch.degree
            lines += ["", f"{EMOJIS[current]} **{LABELS[current]}** · {DEGREE_HINT[current]}"]
        kind = ch.kind
        d = detail(ch)
        if d and ch.kind == MODIFIE:
            kind = f"{kind} ({d})"
        lines.append(f"{KIND_EMOJI[ch.kind]} **{kind}** — {subject(ch.course)} · {fmt_slot(ch.course)}")
    if pdf_sent:
        lines += ["", "📎 Rapport PDF détaillé envoyé en pièce jointe."]
    elif all_room_only(changes) and sum(1 for c in changes if c.degree in (URGENT, IMPORTANT)) > 5:
        lines += ["", "Uniquement des changements de salle cette fois — pas de rapport PDF."]
    return "\n".join(lines)


def log_message(changes: list[Change], now: datetime, pdf_sent: bool, dm_ok: bool) -> str:
    """Message détaillé pour le salon de logs."""
    head = (f"🕐 **{fmt_detection(now)}** — {_plural(len(changes), 'changement')} "
            f"{'détecté' if len(changes) == 1 else 'détectés'} · DM {'envoyé ✅' if dm_ok else 'en échec ⚠️'}"
            f" · PDF : {'oui' if pdf_sent else 'non'}")
    lines = [head]
    for ch in sorted(changes, key=Change.sort_key):
        c = shown(ch)
        d = detail(ch)
        bits = [f"{EMOJIS[ch.degree]} {ch.degree}", f"{KIND_EMOJI[ch.kind]} {ch.kind}", subject(c),
                fmt_slot(c), dash(c.enseignant), dash(c.salle)]
        line = " · ".join(bits)
        if d:
            line += f"\n  ↳ {d}"
        lines.append("• " + line)
    return "\n".join(lines)


def log_no_change(now: datetime, count: int) -> str:
    return f"🕐 {fmt_detection(now)} — ✅ Aucun changement ({count} cours suivis)"


def log_baseline(now: datetime, count: int) -> str:
    return (f"🕐 **{fmt_detection(now)}** — 📥 Première exécution : {count} cours enregistrés comme "
            "référence. Aucune alerte envoyée ; les prochains changements seront signalés.")
