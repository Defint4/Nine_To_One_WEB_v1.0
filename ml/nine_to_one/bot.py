"""Bot de table : crée une partie, se met prêt, joue ses tours avec un délai humain.

Suit les revanches. S'arrête avec le process.
"""

import asyncio
import json
import random
import sys
import urllib.request

API = "http://127.0.0.1:8004"
WS = "ws://127.0.0.1:8004"
PSEUDO = "Claude"
AVATAR = "renard-0"

import websockets  # noqa: E402


def post(path: str, payload: dict | None, token: str | None = None) -> dict:
    req = urllib.request.Request(
        API + path,
        data=json.dumps(payload or {}).encode(),
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as res:
        return json.loads(res.read())


async def play_room(token: str, code: str) -> str | None:
    """Joue dans une table jusqu'à sa fin ; renvoie le code de revanche s'il y en a une."""
    my_seat = None
    view = None
    async with websockets.connect(f"{WS}/api/rooms/{code}/ws?token={token}") as ws:
        await ws.send(json.dumps({"action": "ready"}))
        print(f"[bot] prêt sur la table {code}", flush=True)
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=60)
            except asyncio.TimeoutError:
                continue
            msg = json.loads(raw)
            if msg["type"] == "rematch":
                return msg["code"]
            if msg["type"] != "state":
                continue
            view = msg["view"]
            my_seat = view["your_seat"]
            if view["status"] != "playing" or view["turn"] != my_seat:
                continue
            # Petit délai pour un rythme naturel, puis vérifie que c'est toujours à nous.
            await asyncio.sleep(random.uniform(0.9, 1.7))
            try:
                extra = json.loads(await asyncio.wait_for(ws.recv(), timeout=0.05))
                if extra["type"] == "state":
                    view = extra["view"]
            except (asyncio.TimeoutError, KeyError):
                pass
            if view["status"] != "playing" or view["turn"] != my_seat:
                continue
            me = view["players"][my_seat]
            if view["must_flip"]:
                index = random.randrange(me["face_down_count"])
                await ws.send(json.dumps({"action": "flip", "index": index}))
            elif view["playable_values"]:
                value = random.choice(view["playable_values"])
                copies = len([c for c in (me["hand"] or []) if c["value"] == value])
                count = random.randint(1, max(copies, 1))
                payload = {"action": "play", "value": value, "count": count}
                if value == 7:
                    payload["direction"] = random.choice([">=", "<="])
                await ws.send(json.dumps(payload))


async def main() -> None:
    token = post("/api/players/enter", {"pseudo": PSEUDO, "avatar": AVATAR})["token"]
    code = post("/api/rooms", None, token)["code"]
    print(f"TABLE={code}", flush=True)
    while True:
        try:
            next_code = await play_room(token, code)
        except Exception as exc:  # coupure réseau, table supprimée…
            print(f"[bot] reconnexion ({exc})", flush=True)
            await asyncio.sleep(2)
            continue
        if next_code:
            post(f"/api/rooms/{next_code}/join", None, token)
            print(f"[bot] revanche -> table {next_code}", flush=True)
            code = next_code
        else:
            await asyncio.sleep(2)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
