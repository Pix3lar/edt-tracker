"""Téléchargement et lecture du calendrier ICS exporté par Hyperplanning."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone

import requests
from icalendar import Calendar

# Clés connues dans la DESCRIPTION Hyperplanning ("Matière : ...", "Salle : ...")
KNOWN_KEYS = {"matière", "matiere", "enseignant", "enseignants", "promotion", "promotions",
              "salle", "salles", "type", "td", "tp", "groupe", "groupes", "mémo", "memo"}

# Préfixes de statut ajoutés par Hyperplanning devant le titre d'un cours
STATUS_PREFIX_RE = re.compile(r"^\s*(Annulation|Annulé|Reporté[^:]*|Modifié[^:]*|Exceptionnel[^:]*)\s*:\s*", re.I)


class FetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class Course:
    uid: str
    start: str            # ISO 8601 UTC, ex. 2026-10-05T12:00:00+00:00
    end: str
    matiere: str
    enseignant: str
    salle: str
    type: str
    statut: str           # "" pour un cours normal, sinon "Annulation", "Reporté (date ultérieure)"...
    summary: str

    @property
    def start_dt(self) -> datetime:
        return datetime.fromisoformat(self.start)

    @property
    def end_dt(self) -> datetime:
        return datetime.fromisoformat(self.end)

    @property
    def is_status_marker(self) -> bool:
        """Événement « Annulation : … » / « Reporté : … » (pas un vrai cours)."""
        return bool(self.statut)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Course":
        return Course(**d)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _to_utc_iso(value) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):  # événement « journée entière »
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc).isoformat()
    raise ValueError(f"date inattendue : {value!r}")


def _parse_description(desc: str) -> tuple[dict, str]:
    """Retourne ({clé: valeur}, statut) depuis la DESCRIPTION Hyperplanning."""
    fields: dict[str, str] = {}
    statut = ""
    for line in (desc or "").replace("\r", "").split("\n"):
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key_n = _clean(key).lower()
        value = _clean(value)
        if key_n in KNOWN_KEYS:
            fields.setdefault(key_n, value)
        elif not value and not statut and key_n:
            statut = _clean(key)  # ex. "Annulation : " (valeur vide)
    return fields, statut


def parse_ics(text: str | bytes) -> dict[str, Course]:
    cal = Calendar.from_ical(text)
    courses: dict[str, Course] = {}
    for comp in cal.walk("VEVENT"):
        uid = str(comp.get("UID", "")).strip()
        if not uid or comp.get("DTSTART") is None:
            continue
        summary = _clean(str(comp.get("SUMMARY", "")))
        fields, statut = _parse_description(str(comp.get("DESCRIPTION", "")))
        m = STATUS_PREFIX_RE.match(summary)
        if not statut and m:
            statut = _clean(m.group(1))
        if not statut and uid.upper().startswith("COURSANNULE"):
            statut = "Annulation"
        bare_summary = STATUS_PREFIX_RE.sub("", summary)
        parts = [p.strip() for p in bare_summary.split(" - ")]

        start = comp.decoded("DTSTART")
        end = comp.decoded("DTEND") if comp.get("DTEND") is not None else start
        matiere = fields.get("matière") or fields.get("matiere") or (parts[0] if parts else "")
        enseignant = fields.get("enseignant") or fields.get("enseignants") or ""
        salle = fields.get("salle") or fields.get("salles") or _clean(str(comp.get("LOCATION", "")))
        ctype = fields.get("type") or (parts[-1] if len(parts) >= 2 else "")

        courses[uid] = Course(
            uid=uid,
            start=_to_utc_iso(start),
            end=_to_utc_iso(end),
            matiere=_clean(matiere),
            enseignant=_clean(enseignant),
            salle=_clean(salle),
            type=_clean(ctype),
            statut=statut,
            summary=summary,
        )
    return courses


def fetch_ics(url: str, timeout: int = 30, session: requests.Session | None = None) -> str:
    http = session or requests
    last_err: Exception | None = None
    for _ in range(3):
        try:
            r = http.get(url, timeout=timeout, headers={"User-Agent": "edt-bot/1.0"})
            if r.status_code == 200 and "BEGIN:VCALENDAR" in r.text:
                return r.text
            last_err = FetchError(f"HTTP {r.status_code}" if r.status_code != 200 else "réponse qui n'est pas un calendrier ICS")
        except requests.RequestException as e:  # réseau, timeout...
            last_err = FetchError(type(e).__name__)
    raise last_err or FetchError("échec inconnu")
