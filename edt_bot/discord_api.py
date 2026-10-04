"""Petit client Discord (API REST) : DM et messages dans un salon, avec pièces jointes."""

from __future__ import annotations

import json
import os
import time

import requests

DEFAULT_API = "https://discord.com/api/v10"
GATEWAY = "wss://gateway.discord.gg/?v=10&encoding=json"
MAX_LEN = 2000


class DiscordError(RuntimeError):
    pass


def split_message(text: str, limit: int = MAX_LEN) -> list[str]:
    """Découpe un texte trop long en plusieurs messages, sur des fins de ligne."""
    chunks, cur = [], ""
    for line in text.split("\n"):
        while len(line) > limit:  # ligne seule trop longue
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(line[:limit])
            line = line[limit:]
        candidate = f"{cur}\n{line}" if cur else line
        if len(candidate) > limit:
            chunks.append(cur)
            cur = line
        else:
            cur = candidate
    if cur:
        chunks.append(cur)
    return chunks or [""]


class Discord:
    def __init__(self, token: str, session: requests.Session | None = None, api_base: str | None = None):
        self.token = token
        self.api = (api_base or os.environ.get("DISCORD_API_BASE") or DEFAULT_API).rstrip("/")
        self.http = session or requests.Session()
        self._dm_cache: dict[str, str] = {}

    # --- bas niveau -------------------------------------------------------
    def _request(self, method: str, path: str, **kw) -> dict:
        headers = {"Authorization": f"Bot {self.token}",
                   "User-Agent": "DiscordBot (https://github.com, 1.0) edt-bot"}
        for attempt in range(5):
            r = self.http.request(method, self.api + path, headers=headers, timeout=30, **kw)
            if r.status_code == 429:  # limite de débit : on attend ce que Discord demande
                try:
                    wait = float(r.json().get("retry_after", 1))
                except ValueError:
                    wait = 1.0
                time.sleep(min(wait, 30) + 0.2)
                continue
            if r.status_code >= 500 and attempt < 4:
                time.sleep(2 * (attempt + 1))
                continue
            if r.status_code >= 400:
                try:
                    detail = r.json().get("message", "")
                except ValueError:
                    detail = ""
                raise DiscordError(f"{method} {path.split('/')[1]} → HTTP {r.status_code} {detail}".strip())
            return r.json() if r.content else {}
        raise DiscordError("trop de tentatives (limite de débit)")

    # --- haut niveau ------------------------------------------------------
    def me(self) -> dict:
        return self._request("GET", "/users/@me")

    def dm_channel(self, user_id: str) -> str:
        if user_id not in self._dm_cache:
            data = self._request("POST", "/users/@me/channels", json={"recipient_id": str(user_id)})
            self._dm_cache[user_id] = data["id"]
        return self._dm_cache[user_id]

    def send(self, channel_id: str, text: str, files: list[str] | None = None) -> None:
        chunks = split_message(text)
        for i, chunk in enumerate(chunks):
            payload = {"content": chunk, "allowed_mentions": {"parse": []}}
            last = i == len(chunks) - 1
            if files and last:
                handles = [open(p, "rb") for p in files]
                try:
                    payload["attachments"] = [{"id": n, "filename": os.path.basename(p)} for n, p in enumerate(files)]
                    multipart = {"payload_json": (None, json.dumps(payload), "application/json")}
                    for n, (p, h) in enumerate(zip(files, handles)):
                        multipart[f"files[{n}]"] = (os.path.basename(p), h, "application/pdf")
                    self._request("POST", f"/channels/{channel_id}/messages", files=multipart)
                finally:
                    for h in handles:
                        h.close()
            else:
                self._request("POST", f"/channels/{channel_id}/messages", json=payload)

    def send_dm(self, user_id: str, text: str, files: list[str] | None = None) -> None:
        self.send(self.dm_channel(user_id), text, files)

    def identify_once(self) -> str:
        """Connexion unique à la passerelle Discord.

        Discord exige qu'un bot se soit connecté au moins une fois à la
        passerelle avant de pouvoir envoyer des messages via l'API REST.
        """
        import websocket  # paquet websocket-client

        ws = websocket.create_connection(GATEWAY, timeout=20)
        try:
            hello = json.loads(ws.recv())
            if hello.get("op") != 10:
                raise DiscordError("réponse inattendue de la passerelle")
            ws.send(json.dumps({"op": 2, "d": {"token": self.token, "intents": 0,
                                               "properties": {"os": "linux", "browser": "edt-bot", "device": "edt-bot"}}}))
            deadline = time.time() + 20
            while time.time() < deadline:
                msg = json.loads(ws.recv())
                if msg.get("op") == 0 and msg.get("t") == "READY":
                    return msg["d"]["user"]["username"]
                if msg.get("op") == 9:
                    raise DiscordError("jeton refusé par la passerelle")
            raise DiscordError("pas de réponse READY")
        finally:
            ws.close()
