"""Rapport PDF détaillé (généré quand il y a plus de 5 changements urgents/importants)."""

from __future__ import annotations

import os
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from xml.sax.saxutils import escape

from .diff import Change, local
from .formatting import dash, detail, fmt_slot, shown, subject
from .priority import LABELS

BADGE = {"A": colors.HexColor("#D93025"), "B": colors.HexColor("#E8710A"),
         "C": colors.HexColor("#F2B600"), "D": colors.HexColor("#9AA0A6")}
INK = colors.HexColor("#1F2328")
MUTED = colors.HexColor("#5F6368")
LINE = colors.HexColor("#DADCE0")
GROUP_BG = colors.HexColor("#EEF1F5")


def report_filename(now: datetime) -> str:
    return f"rapport-emploi-du-temps-{local(now):%Y-%m-%d}.pdf"


def build_report(changes: list[Change], now: datetime, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, report_filename(now))
    styles = getSampleStyleSheet()
    cell = ParagraphStyle("cell", parent=styles["BodyText"], fontSize=8.5, leading=10.5, textColor=INK)
    small = ParagraphStyle("small", parent=cell, fontSize=7.5, leading=9.5, textColor=MUTED)
    badge = ParagraphStyle("badge", parent=cell, fontName="Helvetica-Bold", textColor=colors.white,
                           alignment=TA_CENTER, fontSize=8)
    head = ParagraphStyle("head", parent=cell, fontName="Helvetica-Bold", textColor=colors.white)
    title = ParagraphStyle("title", parent=styles["Title"], fontSize=17, leading=21, textColor=INK, alignment=0)
    sub = ParagraphStyle("sub", parent=cell, fontSize=9.5, textColor=MUTED)

    doc = SimpleDocTemplate(path, pagesize=landscape(A4), leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=13 * mm, bottomMargin=13 * mm,
                            title="Rapport — changements d'emploi du temps", author="edt-bot")
    d = local(now)
    counts = {k: sum(1 for c in changes if c.degree == k) for k in "ABCD"}
    summary = " · ".join(f"{LABELS[k]} : {v}" for k, v in counts.items() if v)
    story = [
        Paragraph("Changements d'emploi du temps — B2 INFO Martinique", title),
        Paragraph(f"Rapport du {d:%d/%m/%Y} · {len(changes)} changement(s) · {summary}", sub),
        Spacer(1, 6 * mm),
    ]

    header = ["Degré", "Type", "Matière", "Enseignant", "Salle", "Date / heure", "Détail"]
    rows = [[Paragraph(h, head) for h in header]]
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    # Toutes les détections d'une exécution ont la même heure : affichée une seule fois en en-tête de groupe
    rows.append([Paragraph(f"<b>Détecté le {d:%d/%m/%Y} à {d:%Hh%M}</b>", cell)] + [""] * 6)
    style += [("SPAN", (0, 1), (-1, 1)), ("BACKGROUND", (0, 1), (-1, 1), GROUP_BG)]

    for ch in sorted(changes, key=Change.sort_key):
        c = shown(ch)
        r = len(rows)
        rows.append([
            Paragraph(f"{ch.degree} · {LABELS[ch.degree]}", badge),
            Paragraph(escape(ch.kind), cell),
            Paragraph(escape(subject(c)), cell),
            Paragraph(escape(dash(c.enseignant)), cell),
            Paragraph(escape(dash(c.salle)), cell),   # colonne Salle obligatoire, « — » si vide
            Paragraph(escape(fmt_slot(c)), cell),
            Paragraph(escape(detail(ch) or "—"), small),
        ])
        style.append(("BACKGROUND", (0, r), (0, r), BADGE[ch.degree]))

    widths = [26 * mm, 30 * mm, 62 * mm, 30 * mm, 24 * mm, 40 * mm, 57 * mm]
    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle(style))
    story.append(table)
    doc.build(story)
    return path
