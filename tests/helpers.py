"""Fabrique de calendriers ICS au format Hyperplanning, pour les tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from icalendar import Calendar, Event

from edt_bot.ics import Course

AST = timezone(timedelta(hours=-4))  # heure de Martinique


def at(y, mo, d, h, mi=0) -> datetime:
    """Date/heure locale Martinique → UTC."""
    return datetime(y, mo, d, h, mi, tzinfo=AST).astimezone(timezone.utc)


def course(uid, start: datetime, hours=2.0, matiere="R3.01 Développement web", enseignant="JEAN",
           salle="Salle i4", ctype="TP", statut="") -> Course:
    end = start + timedelta(hours=hours)
    title = f"{matiere} - {enseignant} - B2 INFO Martinique - {ctype}"
    if statut:
        title = f"{statut} : {title}"
    return Course(uid=uid, start=start.isoformat(), end=end.isoformat(), matiere=matiere,
                  enseignant=enseignant, salle=salle, type=ctype, statut=statut, summary=title)


def to_ics(courses) -> str:
    cal = Calendar()
    cal.add("prodid", "-//INDEX EDUCATION//HYPERPLANNING//FR")
    cal.add("version", "2.0")
    for c in courses:
        ev = Event()
        ev.add("uid", c.uid)
        ev.add("dtstamp", datetime(2026, 10, 4, 11, 13, tzinfo=timezone.utc))
        ev.add("dtstart", c.start_dt)
        ev.add("dtend", c.end_dt)
        ev.add("summary", c.summary)
        desc = ""
        if c.statut:
            desc += f"{c.statut} : \n"
        desc += f"Matière : {c.matiere}\nEnseignant : {c.enseignant}\nPromotion : B2 INFO Martinique\n"
        if c.salle:
            desc += f"Salle : {c.salle}\n"
            ev.add("location", c.salle)
        desc += f"Type : {c.type}\n"
        ev.add("description", desc)
        cal.add_component(ev)
    return cal.to_ical().decode()


def by_uid(courses) -> dict[str, Course]:
    return {c.uid: c for c in courses}


def base_week() -> list[Course]:
    """Une semaine type (5 → 10 octobre 2026) + quelques cours plus tard, inspirée du vrai EDT."""
    L = [
        course("Cours-1-6", at(2026, 10, 5, 8), matiere="R3.07 SQL dans un langage de", ctype="Cours"),
        course("Cours-2-6", at(2026, 10, 5, 10), matiere="R3.07 SQL dans un langage de", enseignant="LASSERRE", ctype="TD"),
        course("Cours-3-6", at(2026, 10, 6, 8), matiere="R3.10 Management des systèmes", enseignant="JOSEPH"),
        course("Cours-4-6", at(2026, 10, 6, 10), matiere="R3.17 Calcul scientifique 2", enseignant="MOLA"),
        course("Cours-5-6", at(2026, 10, 7, 8), matiere="R3.15 IA Introduction aux modé"),
        course("Cours-6-6", at(2026, 10, 8, 10), hours=1, matiere="R3.16 Fouille de données ( Dat", enseignant="ZONGO", ctype="CM"),
        course("Cours-7-6", at(2026, 10, 9, 8), matiere="R3.16 Fouille de données ( Dat", enseignant="ZONGO", ctype="CM"),
        course("Cours-8-6", at(2026, 10, 14, 8), matiere="R3.07 SQL dans un langage de", enseignant="LASSERRE", ctype="TD"),
        course("Cours-9-6", at(2026, 10, 22, 13, 30), matiere="R3.12 Anglais", enseignant="THEODORE", salle="Salle H2 bis", ctype="TD"),
        course("Cours-10-6", at(2026, 10, 28, 8), matiere="R3.08 Probabilités", enseignant="ZONGO", ctype="TD"),
        course("Cours-11-6", at(2026, 11, 18, 8), matiere="R3.04 Qualité de développement", enseignant="LABEJOF", ctype="CM"),
    ]
    # Cours passés (déjà terminés le 4 octobre) : ne doivent jamais déclencher d'alerte
    L.append(course("Cours-90-6", at(2026, 9, 30, 11), hours=1, matiere="R3.16 Fouille de données ( Dat", enseignant="ZONGO", salle="Salle H2", ctype="CM"))
    # Assez de cours pour ne pas déclencher le garde-fou « EDT presque vide »
    for i in range(20):
        L.append(course(f"Cours-{200 + i}-6", at(2027, 1, 4 + (i % 5), 8 + 2 * (i // 5)), matiere=f"R4.{i:02d} Module", ctype="TD"))
    return L
