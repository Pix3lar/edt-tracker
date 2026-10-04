"""Degrés d'importance A/B/C/D (règles définies avec Jeffrey en septembre 2026)."""

from __future__ import annotations

from datetime import date, timedelta

URGENT, IMPORTANT, MOYEN, FAIBLE = "A", "B", "C", "D"

LABELS = {URGENT: "URGENT", IMPORTANT: "IMPORTANT", MOYEN: "MOYEN", FAIBLE: "FAIBLE"}
EMOJIS = {URGENT: "🔴", IMPORTANT: "🟠", MOYEN: "🟡", FAIBLE: "⚪"}
ORDER = {URGENT: 0, IMPORTANT: 1, MOYEN: 2, FAIBLE: 3}


def current_week_monday(today: date) -> date:
    """Lundi de la « semaine en cours » (lundi → samedi).

    Le dimanche n'appartient à aucune semaine lundi-samedi : ce jour-là, la
    semaine en cours est celle qui commence le lendemain (sinon les cours de
    lundi ne seraient jamais « urgents » quand on regarde le dimanche).
    """
    if today.weekday() == 6:  # dimanche
        return today + timedelta(days=1)
    return today - timedelta(days=today.weekday())


def degree(course_day: date, today: date) -> str:
    monday = current_week_monday(today)
    # A — semaine en cours, lundi → samedi
    if monday <= course_day <= monday + timedelta(days=5):
        return URGENT
    # B — semaine +1 ou +2 (lundi → samedi), même si ça déborde sur le mois suivant
    for k in (1, 2):
        m = monday + timedelta(weeks=k)
        if m <= course_day <= m + timedelta(days=5):
            return IMPORTANT
    # C — plus tard mais dans le mois civil en cours
    if (course_day.year, course_day.month) == (today.year, today.month):
        return MOYEN
    return FAIBLE
