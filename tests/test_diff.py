from dataclasses import replace

from edt_bot.diff import (ANNULATION_LEVEE, ANNULE, MODIFIE, NOUVEAU, REPORTE, SUPPRIME,
                          compute_changes)
from tests.helpers import at, base_week, by_uid, course

NOW = at(2026, 10, 4, 7, 17)  # dimanche 4 octobre, 7h17


def diff(old_list, new_list, now=NOW):
    return compute_changes(by_uid(old_list), by_uid(new_list), now)


def test_no_change():
    assert diff(base_week(), base_week()) == []


def test_new_course():
    new = base_week() + [course("Cours-50-6", at(2026, 10, 7, 13, 30), matiere="R3.12 Anglais")]
    (ch,) = diff(base_week(), new)
    assert ch.kind == NOUVEAU and ch.degree == "A"


def test_room_only_change_same_uid():
    new = [replace(c, salle="Salle H2") if c.uid == "Cours-3-6" else c for c in base_week()]
    (ch,) = diff(base_week(), new)
    assert ch.kind == MODIFIE and ch.changed == ["salle"] and ch.room_only
    assert ch.old.salle == "Salle i4"


def test_room_added_counts_as_room_only():
    old = [replace(c, salle="") if c.uid == "Cours-6-6" else c for c in base_week()]
    (ch,) = diff(old, base_week())
    assert ch.room_only


def test_time_change_is_not_room_only():
    new = []
    for c in base_week():
        if c.uid == "Cours-4-6":
            c = replace(c, start=at(2026, 10, 6, 13, 30).isoformat(), end=at(2026, 10, 6, 15, 30).isoformat(), salle="Salle H2")
        new.append(c)
    (ch,) = diff(base_week(), new)
    assert ch.kind == MODIFIE and set(ch.changed) == {"horaire", "salle"} and not ch.room_only


def test_cancellation_is_paired_with_removed_course():
    """Hyperplanning supprime le cours et crée « Annulation : … » avec un nouvel UID."""
    old = base_week()
    target = next(c for c in old if c.uid == "Cours-2-6")
    marker = replace(target, uid="COURSANNULE-568-6", statut="Annulation", salle="")
    new = [c for c in old if c.uid != "Cours-2-6"] + [marker]
    changes = diff(old, new)
    assert len(changes) == 1
    assert changes[0].kind == ANNULE and changes[0].old.uid == "Cours-2-6"
    assert changes[0].degree == "A"


def test_cancellation_without_twin():
    marker = course("COURSANNULE-9-6", at(2026, 10, 15, 10), matiere="R3.04 Qualité", statut="Annulation")
    (ch,) = diff(base_week(), base_week() + [marker])
    assert ch.kind == ANNULE and ch.degree == "B"


def test_postponed():
    old = base_week()
    t = next(c for c in old if c.uid == "Cours-9-6")
    new = [c for c in old if c.uid != "Cours-9-6"] + [replace(t, uid="COURSANNULE-10-6", statut="Reporté (date ultérieure)")]
    (ch,) = diff(old, new)
    assert ch.kind == REPORTE


def test_removed_course():
    new = [c for c in base_week() if c.uid != "Cours-10-6"]
    (ch,) = diff(base_week(), new)
    assert ch.kind == SUPPRIME and ch.degree == "C"


def test_teacher_swap_with_new_uid_is_a_modification():
    old = base_week()
    t = next(c for c in old if c.uid == "Cours-1-6")
    new = [c for c in old if c.uid != "Cours-1-6"] + [replace(t, uid="Cours-77-6", enseignant="LABEJOF")]
    (ch,) = diff(old, new)
    assert ch.kind == MODIFIE and ch.changed == ["enseignant"]


def test_moved_same_day_with_new_uid():
    old = base_week()
    t = next(c for c in old if c.uid == "Cours-5-6")
    moved = replace(t, uid="Cours-78-6", start=at(2026, 10, 7, 13, 30).isoformat(), end=at(2026, 10, 7, 15, 30).isoformat())
    new = [c for c in old if c.uid != "Cours-5-6"] + [moved]
    (ch,) = diff(old, new)
    assert ch.kind == MODIFIE and ch.changed == ["horaire"]


def test_past_courses_are_ignored():
    new = [c for c in base_week() if c.uid != "Cours-90-6"]  # cours du 30 septembre retiré
    assert diff(base_week(), new) == []


def test_course_restored_after_cancellation():
    old_t = next(c for c in base_week() if c.uid == "Cours-8-6")
    marker = replace(old_t, uid="COURSANNULE-3-6", statut="Annulation")
    old = [c for c in base_week() if c.uid != "Cours-8-6"] + [marker]
    new = base_week()
    (ch,) = diff(old, new)
    assert ch.kind == ANNULATION_LEVEE and ch.course.uid == "Cours-8-6"


def test_moved_far_keeps_urgency_of_old_slot():
    """Cours de mardi déplacé au mois prochain : reste URGENT (tu serais venu mardi pour rien)."""
    new = []
    for c in base_week():
        if c.uid == "Cours-3-6":
            c = replace(c, start=at(2026, 11, 24, 8).isoformat(), end=at(2026, 11, 24, 10).isoformat())
        new.append(c)
    (ch,) = diff(base_week(), new)
    assert ch.degree == "A"


def test_sorting_is_chronological_not_alphabetical():
    """« jeu. » < « lun. » < « mar. » en alphabétique : on vérifie le vrai ordre des jours."""
    new = []
    for c in base_week():
        if c.uid in ("Cours-1-6", "Cours-3-6", "Cours-6-6", "Cours-10-6", "Cours-8-6"):
            c = replace(c, salle="Salle B1")
        new.append(c)
    order = [ch.course.uid for ch in diff(base_week(), new)]
    # A : lun 5, mar 6, jeu 8 — puis B : mer 14 — puis C : mer 28
    assert order == ["Cours-1-6", "Cours-3-6", "Cours-6-6", "Cours-8-6", "Cours-10-6"]
