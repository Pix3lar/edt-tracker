"""Mémoire entre deux exécutions (fichier JSON conservé par le cache GitHub Actions)."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field

from .ics import Course


@dataclass
class State:
    courses: dict[str, Course] | None = None   # None = première exécution
    updated_at: str = ""
    failures: int = 0                           # échecs consécutifs (téléchargement, Discord...)
    failure_alert_sent: bool = False
    suspicious_runs: int = 0                    # exécutions consécutives avec un EDT anormalement vide
    extra: dict = field(default_factory=dict)

    @staticmethod
    def load(path: str) -> "State":
        if not os.path.exists(path):
            return State()
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        courses = raw.get("courses")
        return State(
            courses=None if courses is None else {u: Course.from_dict(c) for u, c in courses.items()},
            updated_at=raw.get("updated_at", ""),
            failures=raw.get("failures", 0),
            failure_alert_sent=raw.get("failure_alert_sent", False),
            suspicious_runs=raw.get("suspicious_runs", 0),
            extra=raw.get("extra", {}),
        )

    def save(self, path: str) -> None:
        data = {
            "version": 1,
            "updated_at": self.updated_at,
            "failures": self.failures,
            "failure_alert_sent": self.failure_alert_sent,
            "suspicious_runs": self.suspicious_runs,
            "extra": self.extra,
            "courses": None if self.courses is None else {u: c.to_dict() for u, c in sorted(self.courses.items())},
        }
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)  # écriture atomique
