import os
from datetime import date

from edt_bot.ics import parse_ics
from edt_bot.priority import degree

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "hyperplanning_sample.ics")


def test_parse_real_hyperplanning_format():
    courses = parse_ics(open(FIX, encoding="utf-8").read())
    assert len(courses) == 4
    c = courses["Cours-36918-6-TRANQUILLE_Jeffrey-Index-Education"]
    assert c.matiere == "R3.07 SQL dans un langage de"   # doubles espaces nettoyés
    assert c.enseignant == "JEAN" and c.salle == "Salle i4" and c.type == "Cours"
    assert c.statut == "" and not c.is_status_marker
    assert c.start == "2026-10-05T12:00:00+00:00"


def test_parse_status_markers():
    courses = parse_ics(open(FIX, encoding="utf-8").read())
    ann = courses["COURSANNULE-568-6-TRANQUILLE_Jeffrey-Index-Education"]
    assert ann.statut == "Annulation" and ann.is_status_marker
    assert ann.matiere == "R3.07 SQL dans un langage de" and ann.enseignant == "LABEJOF"
    rep = courses["COURSANNULE-570-6-TRANQUILLE_Jeffrey-Index-Education"]
    assert rep.statut == "Reporté (date ultérieure)"
    assert rep.salle == "Salle H2"


def test_missing_room_is_empty():
    courses = parse_ics(open(FIX, encoding="utf-8").read())
    assert courses["Cours-18731-6-TRANQUILLE_Jeffrey-Index-Education"].salle == ""


# --- Degrés -----------------------------------------------------------------
SUN = date(2026, 10, 4)   # dimanche (jour de la demande)
WED = date(2026, 10, 21)  # mercredi


def test_sunday_belongs_to_next_week():
    assert degree(date(2026, 10, 5), SUN) == "A"   # lundi
    assert degree(date(2026, 10, 10), SUN) == "A"  # samedi
    assert degree(date(2026, 10, 12), SUN) == "B"  # semaine +1
    assert degree(date(2026, 10, 24), SUN) == "B"  # samedi semaine +2
    assert degree(date(2026, 10, 26), SUN) == "C"  # plus tard en octobre
    assert degree(date(2026, 11, 2), SUN) == "D"


def test_weekday_rules_and_month_overflow():
    assert degree(date(2026, 10, 19), WED) == "A"  # lundi de la semaine en cours
    assert degree(date(2026, 10, 24), WED) == "A"  # samedi
    assert degree(date(2026, 10, 25), WED) == "C"  # dimanche : exclu des fenêtres A/B
    assert degree(date(2026, 10, 31), WED) == "B"
    assert degree(date(2026, 11, 3), WED) == "B"   # déborde sur novembre : B l'emporte
    assert degree(date(2026, 11, 7), WED) == "B"
    assert degree(date(2026, 11, 9), WED) == "D"
