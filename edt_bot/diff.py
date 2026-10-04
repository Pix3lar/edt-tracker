"""Comparaison de deux versions de l'emploi du temps."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from .ics import Course
from .priority import ORDER, degree

TZ = ZoneInfo("America/Martinique")

# Types de changement
NOUVEAU = "Nouveau cours"
MODIFIE = "Modifié"
ANNULE = "Annulé"
REPORTE = "Reporté"
SUPPRIME = "Retiré de l'EDT"
ANNULATION_LEVEE = "Annulation retirée"

TRACKED = {
    "start": "horaire",
    "end": "horaire",
    "salle": "salle",
    "enseignant": "enseignant",
    "matiere": "matière",
    "type": "type",
}


@dataclass
class Change:
    kind: str
    course: Course                     # version actuelle (ou ancienne si retiré)
    old: Course | None = None          # version précédente (modifications, annulations appariées)
    changed: list[str] = field(default_factory=list)  # ex. ["salle"], ["horaire", "salle"]
    degree: str = ""
    ref_start: datetime | None = None  # créneau qui compte pour l'urgence (voir relevant_start)

    @property
    def room_only(self) -> bool:
        """Changement de salle uniquement (même règle que l'ancienne tâche)."""
        return self.kind == MODIFIE and bool(self.changed) and set(self.changed) <= {"salle"}

    def sort_key(self):
        # Tri par degré puis par date/heure réelle (jamais par texte affiché)
        return (ORDER[self.degree], self.ref_start or self.course.start_dt, self.course.matiere)


def local(dt: datetime) -> datetime:
    return dt.astimezone(TZ)


def relevant_start(ch: Change, now: datetime) -> datetime:
    """Date du cours qui compte pour l'urgence.

    Pour un cours déplacé, on prend le créneau à venir le plus proche (ancien
    ou nouveau) : un cours déplacé de demain au mois prochain reste urgent,
    car sans l'alerte tu viendrais demain pour rien.
    """
    candidates = [c for c in (ch.course, ch.old) if c is not None and c.end_dt > now]
    if not candidates:
        candidates = [ch.course]
    return min(c.start_dt for c in candidates)


def _key(c: Course) -> str:
    return c.matiere.casefold()


def compute_changes(old: dict[str, Course], new: dict[str, Course], now: datetime) -> list[Change]:
    """Liste des changements pertinents (cours qui ne sont pas encore terminés)."""

    def upcoming(c: Course) -> bool:
        return c.end_dt > now

    changes: list[Change] = []

    added = [new[u] for u in new.keys() - old.keys() if upcoming(new[u])]
    removed = [old[u] for u in old.keys() - new.keys() if upcoming(old[u])]

    # 1) Modifications d'un même événement (même UID)
    for uid in sorted(new.keys() & old.keys()):
        a, b = old[uid], new[uid]
        if not (upcoming(a) or upcoming(b)):
            continue
        diffs = []
        for attr, label in TRACKED.items():
            if getattr(a, attr) != getattr(b, attr) and label not in diffs:
                diffs.append(label)
        if a.statut != b.statut:
            if b.statut and not a.statut:
                changes.append(Change(_status_kind(b.statut), b, a))
                continue
            if a.statut and not b.statut:
                changes.append(Change(ANNULATION_LEVEE, b, a))
                continue
        if diffs:
            changes.append(Change(MODIFIE, b, a, diffs))

    removed_normal = [c for c in removed if not c.is_status_marker]
    removed_markers = [c for c in removed if c.is_status_marker]
    added_markers = [c for c in added if c.is_status_marker]
    added_normal = [c for c in added if not c.is_status_marker]

    # 2) « Annulation : … » / « Reporté : … » : Hyperplanning supprime le cours
    #    et crée un nouvel événement marqueur → on recolle les deux.
    for mk in sorted(added_markers, key=lambda c: c.start):
        twin = next((c for c in removed_normal if c.start == mk.start and _key(c) == _key(mk)), None)
        if twin:
            removed_normal.remove(twin)
        changes.append(Change(_status_kind(mk.statut), mk, twin))

    # 3) Cours retiré + cours ajouté pour la même matière → modification
    #    a) même créneau (changement d'enseignant / salle / fin)
    for c_new in sorted(list(added_normal), key=lambda c: c.start):
        twin = next((c for c in removed_normal
                     if c.start == c_new.start and _key(c) == _key(c_new) and c.type == c_new.type), None)
        if twin:
            removed_normal.remove(twin)
            added_normal.remove(c_new)
            diffs = [lbl for attr, lbl in TRACKED.items() if getattr(twin, attr) != getattr(c_new, attr)]
            diffs = list(dict.fromkeys(diffs))
            if diffs:
                changes.append(Change(MODIFIE, c_new, twin, diffs))
    #    b) même jour, seul candidat possible (changement d'horaire)
    for c_new in sorted(list(added_normal), key=lambda c: c.start):
        day = local(c_new.start_dt).date()
        cands = [c for c in removed_normal
                 if local(c.start_dt).date() == day and _key(c) == _key(c_new) and c.type == c_new.type]
        same_day_new = [c for c in added_normal
                        if local(c.start_dt).date() == day and _key(c) == _key(c_new) and c.type == c_new.type]
        if len(cands) == 1 and len(same_day_new) == 1:
            twin = cands[0]
            removed_normal.remove(twin)
            added_normal.remove(c_new)
            diffs = list(dict.fromkeys(lbl for attr, lbl in TRACKED.items()
                                       if getattr(twin, attr) != getattr(c_new, attr)))
            changes.append(Change(MODIFIE, c_new, twin, diffs))

    # 4) Marqueur « Annulation » qui disparaît : le cours est rétabli
    for mk in removed_markers:
        back = next((c for c in added_normal if c.start == mk.start and _key(c) == _key(mk)), None)
        if back:
            added_normal.remove(back)
            changes.append(Change(ANNULATION_LEVEE, back, mk))
        else:
            changes.append(Change(ANNULATION_LEVEE, mk))

    # 5) Le reste
    changes += [Change(NOUVEAU, c) for c in added_normal]
    changes += [Change(SUPPRIME, c) for c in removed_normal]

    today = local(now).date()
    for ch in changes:
        ch.ref_start = relevant_start(ch, now)
        ch.degree = degree(local(ch.ref_start).date(), today)
    changes.sort(key=Change.sort_key)
    return changes


def _status_kind(statut: str) -> str:
    return REPORTE if statut.lower().startswith("report") else ANNULE
