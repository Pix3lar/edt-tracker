"""Tests de bout en bout du programme (Discord simulé)."""

from dataclasses import replace

import pytest

from edt_bot.__main__ import Config, Out, run
from edt_bot.discord_api import DiscordError
from edt_bot.state import State
from tests.helpers import at, base_week, to_ics

NOW = "2026-10-04T07:17:00-04:00"


class FakeOut(Out):
    def __init__(self, cfg, fail_dm=False):
        super().__init__(cfg)
        self.fail_dm = fail_dm

    def dm(self, text, files=None):
        if self.fail_dm:
            raise DiscordError("POST channels → HTTP 403 Cannot send messages to this user")
        self.sent.append(("dm", text, files or []))

    def log(self, text):
        self.sent.append(("log", text, []))
        return True


@pytest.fixture
def env(tmp_path, monkeypatch):
    ics = tmp_path / "edt.ics"
    monkeypatch.setenv("ICS_URL", str(ics))
    monkeypatch.setenv("STATE_FILE", str(tmp_path / "state" / "state.json"))
    monkeypatch.setenv("REPORT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("EDT_NOW", NOW)
    monkeypatch.delenv("LOG_QUIET_RUNS", raising=False)

    class Env:
        path = ics

        def write(self, courses):
            ics.write_text(to_ics(courses), encoding="utf-8")

        def run(self, **kw):
            cfg = Config(dry_run=True)
            out = FakeOut(cfg, **kw)
            code = run(cfg, out)
            return code, out.sent

        def state(self):
            return State.load(str(tmp_path / "state" / "state.json"))

    return Env()


def kinds(sent):
    return [k for k, _, _ in sent]


def test_first_run_is_silent_baseline(env):
    env.write(base_week())
    code, sent = env.run()
    assert code == 0 and kinds(sent) == ["log"]
    assert "Première exécution" in sent[0][1]
    assert len(env.state().courses) == len(base_week())


def test_no_change_never_sends_dm(env, monkeypatch):
    env.write(base_week())
    env.run()
    code, sent = env.run()
    assert code == 0 and kinds(sent) == ["log"] and "Aucun changement" in sent[0][1]
    monkeypatch.setenv("LOG_QUIET_RUNS", "false")
    code, sent = env.run()
    assert sent == []


def test_change_sends_dm_and_log_once(env):
    env.write(base_week())
    env.run()
    env.write([replace(c, salle="Salle H2") if c.uid == "Cours-3-6" else c for c in base_week()])
    code, sent = env.run()
    assert code == 0 and kinds(sent) == ["dm", "log"]
    assert "salle : Salle i4 → Salle H2" in sent[0][1] and sent[0][2] == []
    # Le même changement n'est jamais re-signalé
    code, sent = env.run()
    assert kinds(sent) == ["log"] and "Aucun changement" in sent[0][1]


def test_big_batch_sends_pdf(env):
    env.write(base_week())
    env.run()
    ids = {"Cours-1-6", "Cours-2-6", "Cours-3-6", "Cours-4-6", "Cours-5-6", "Cours-8-6"}
    env.write([replace(c, enseignant="LABEJOF") if c.uid in ids else c for c in base_week()])
    code, sent = env.run()
    dm = sent[0]
    assert dm[0] == "dm" and len(dm[2]) == 1 and dm[2][0].endswith(".pdf")
    assert "📎 Rapport PDF" in dm[1]


def test_failed_dm_keeps_state_for_retry(env):
    env.write(base_week())
    env.run()
    env.write([replace(c, salle="Salle H2") if c.uid == "Cours-3-6" else c for c in base_week()])
    code, sent = env.run(fail_dm=True)
    assert code == 1 and kinds(sent) == ["log"] and "DM en échec" in sent[0][1]
    code, sent = env.run()  # Discord refonctionne : le changement est bien envoyé
    assert kinds(sent) == ["dm", "log"]


def test_download_failures_alert_once_then_recover(env):
    env.write(base_week())
    env.run()
    env.path.write_text("<html>Maintenance</html>", encoding="utf-8")
    dms = []
    for _ in range(5):
        code, sent = env.run()
        assert code == 0
        dms += [t for k, t, _ in sent if k == "dm"]
    assert len(dms) == 1 and "échoue" in dms[0]
    assert len(env.state().courses) == len(base_week())  # référence intacte
    env.write(base_week())
    code, sent = env.run()
    assert ("dm", "✅ Le suivi de l'emploi du temps refonctionne.", []) in sent


def test_suspiciously_small_calendar_is_ignored_then_accepted(env):
    env.write(base_week())
    env.run()
    env.write(base_week()[:3])
    for _ in range(2):
        code, sent = env.run()
        assert kinds(sent) == ["log"] and "Probable souci" in sent[0][1]
    code, sent = env.run()
    assert kinds(sent) == ["log"] and "nouvelle référence" in sent[0][1]
    assert len(env.state().courses) == 3


def test_console_output_has_no_course_details(env, capsys):
    """Le dépôt est public : la console ne doit contenir aucun nom de cours, d'enseignant ou de salle."""
    env.write(base_week())
    env.run()
    env.write([replace(c, salle="Salle SECRETE") if c.uid == "Cours-3-6" else c for c in base_week()])
    env.run()
    out = capsys.readouterr()
    for secret in ("SECRETE", "Management", "JOSEPH", "Salle"):
        assert secret not in out.out + out.err


def test_demo_mode(env):
    from edt_bot.__main__ import demo
    env.write(base_week())
    cfg = Config(dry_run=True)
    out = FakeOut(cfg)
    assert demo(cfg, out) == 0
    dm = out.sent[0]
    assert dm[0] == "dm" and "DÉMO" in dm[1] and dm[2][0].endswith(".pdf")
    assert env.state().courses is None  # la démo ne touche pas à la mémoire


def test_gateway_identify(monkeypatch):
    import json
    import websocket
    from edt_bot.discord_api import Discord

    class FakeWS:
        def __init__(self):
            self.inbox = [{"op": 10, "d": {"heartbeat_interval": 41250}},
                          {"op": 0, "t": "READY", "d": {"user": {"username": "EDT Bot"}}}]
            self.sent = []

        def recv(self):
            return json.dumps(self.inbox.pop(0))

        def send(self, data):
            self.sent.append(json.loads(data))

        def close(self):
            pass

    ws = FakeWS()
    monkeypatch.setattr(websocket, "create_connection", lambda *a, **k: ws)
    assert Discord("tok").identify_once() == "EDT Bot"
    assert ws.sent[0]["op"] == 2 and ws.sent[0]["d"]["token"] == "tok"
