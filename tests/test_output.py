from dataclasses import replace

from pypdf import PdfReader

from edt_bot.diff import compute_changes
from edt_bot.discord_api import split_message
from edt_bot.formatting import dm_message, log_message, needs_pdf
from edt_bot.report import build_report, report_filename
from tests.helpers import at, base_week, by_uid, course

NOW = at(2026, 10, 4, 7, 17)
URGENT_IDS = ["Cours-1-6", "Cours-2-6", "Cours-3-6", "Cours-4-6", "Cours-5-6", "Cours-6-6"]


def changes_with(fn, ids):
    new = [fn(c) if c.uid in ids else c for c in base_week()]
    return compute_changes(by_uid(base_week()), by_uid(new), NOW)


def test_pdf_rule_more_than_five_urgent():
    ch = changes_with(lambda c: replace(c, enseignant="X"), URGENT_IDS)
    assert len(ch) == 6 and needs_pdf(ch)
    assert not needs_pdf(ch[:5])  # 5 = pas strictement plus de 5


def test_pdf_rule_room_only_exception():
    ch = changes_with(lambda c: replace(c, salle="Salle H2"), URGENT_IDS)
    assert len(ch) == 6 and not needs_pdf(ch)
    msg = dm_message(ch, NOW, pdf_sent=False)
    assert "Uniquement des changements de salle" in msg


def test_pdf_rule_counts_only_urgent_and_important():
    ids = ["Cours-9-6", "Cours-10-6", "Cours-11-6"] + [f"Cours-{200 + i}-6" for i in range(5)]
    ch = changes_with(lambda c: replace(c, enseignant="X"), ids)
    assert len(ch) == 8 and not needs_pdf(ch)  # tout en C/D


def test_dm_grouped_by_degree_then_date():
    ch = changes_with(lambda c: replace(c, enseignant="X"), ["Cours-10-6", "Cours-1-6", "Cours-8-6"])
    msg = dm_message(ch, NOW, pdf_sent=True)
    assert msg.index("URGENT") < msg.index("IMPORTANT") < msg.index("MOYEN")
    assert "Détecté dim. 04/10 à 07h17" in msg
    assert msg.count("Détecté") == 1  # heure affichée une seule fois
    assert "lun. 05/10 · 08h00–10h00" in msg
    assert "enseignant : JEAN → X" in msg
    assert msg.strip().endswith("📎 Rapport PDF détaillé envoyé en pièce jointe.")


def test_log_shows_dash_for_missing_room():
    new = base_week() + [course("Cours-60-6", at(2026, 10, 9, 13, 30), salle="")]
    ch = compute_changes(by_uid(base_week()), by_uid(new), NOW)
    log = log_message(ch, NOW, False, True)
    assert "· —" in log and "🆕 Nouveau cours" in log


def test_pdf_report(tmp_path):
    def mutate(c):
        return replace(c, enseignant="X", salle="" if c.uid == "Cours-2-6" else c.salle)
    ch = changes_with(mutate, URGENT_IDS + ["Cours-8-6", "Cours-11-6"])
    path = build_report(ch, NOW, str(tmp_path))
    assert path.endswith("rapport-emploi-du-temps-2026-10-04.pdf")
    text = "".join(p.extract_text() for p in PdfReader(path).pages)
    for word in ["Salle", "Enseignant", "URGENT", "IMPORTANT", "FAIBLE", "Détecté le 04/10/2026 à 07h17"]:
        assert word in text
    assert text.count("Détecté le") == 1
    assert "—" in text  # salle absente
    assert text.index("lun. 05/10") < text.index("mar. 06/10") < text.index("mer. 14/10")


def test_report_filename_uses_local_date():
    assert report_filename(at(2026, 10, 4, 22, 30)) == "rapport-emploi-du-temps-2026-10-04.pdf"  # 02h30 UTC le 5


def test_split_long_messages():
    text = "\n".join(f"ligne {i} " + "x" * 80 for i in range(100))
    parts = split_message(text)
    assert len(parts) > 1 and all(len(p) <= 2000 for p in parts)
    assert "\n".join(parts) == text


def test_cancellation_shows_original_room():
    old = base_week()
    t = next(c for c in old if c.uid == "Cours-2-6")
    new = [c for c in old if c.uid != "Cours-2-6"] + [replace(t, uid="COURSANNULE-1-6", statut="Annulation", salle="")]
    ch = compute_changes(by_uid(old), by_uid(new), NOW)
    assert "LASSERRE · Salle i4" in log_message(ch, NOW, False, True)
