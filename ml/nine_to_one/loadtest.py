"""Test de charge : N tables en parallèle, chacune avec K bots + un « humain » aléatoire.

Mesure ce que voit un joueur : le temps de réponse des bots (entre le moment où c'est
au tour d'un bot et son coup). Si ce temps dépasse nettement délai humain + budget de
réflexion, le serveur sature (file d'attente des réflexions).

Usage : python ml/nine_to_one/loadtest.py --api https://games.matthieuguiot.dev --tables 5 --bots 3
"""

import argparse
import asyncio
import json
import random
import statistics
import time
import urllib.request

import websockets

# Derrière le proxy Cloudflare, un User-Agent « script » prend un 403 sur les POST.
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"


def post(api: str, path: str, payload: dict | None, token: str | None = None) -> dict:
    req = urllib.request.Request(
        api + path,
        data=json.dumps(payload or {}).encode(),
        headers={
            "Content-Type": "application/json",
            "User-Agent": UA,
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as res:
        return json.loads(res.read())


async def play_table(api: str, ws_base: str, idx: int, bots: int, difficulty: str, latencies: list):
    token = post(api, "/api/players/enter", {"pseudo": f"charge_{idx}", "avatar": "chat-0"})["token"]
    code = post(api, "/api/rooms", None, token)["code"]
    my_seat = None
    bot_turn_since: dict[int, float] = {}
    started = time.monotonic()
    moves = 0
    async with websockets.connect(
        f"{ws_base}/api/rooms/{code}/ws?token={token}", additional_headers={"User-Agent": UA}
    ) as ws:
        for _ in range(bots):
            await ws.send(json.dumps({"action": "add_bot", "difficulty": difficulty}))
            await asyncio.sleep(0.3)
        await ws.send(json.dumps({"action": "ready"}))
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=90)
            except TimeoutError:
                print(f"[table {code}] silence de 90 s, abandon", flush=True)
                return
            msg = json.loads(raw)
            if msg["type"] != "state":
                continue
            view = msg["view"]
            my_seat = view["your_seat"]
            now = time.monotonic()
            # Latence des bots : du passage du tour à un bot jusqu'à son coup (changement de tour).
            turn = view["turn"]
            for seat, t0 in list(bot_turn_since.items()):
                if turn != seat:
                    latencies.append(now - t0)
                    del bot_turn_since[seat]
            if view["status"] == "playing" and turn is not None and turn != my_seat:
                bot_turn_since.setdefault(turn, now)
            if view["status"] == "finished":
                me = view["players"][my_seat]
                print(
                    f"[table {code}] finie en {now - started:.0f}s, {moves} coups humains, "
                    f"rang {me['finish_rank']}",
                    flush=True,
                )
                return
            if view["status"] != "playing" or turn != my_seat:
                continue
            await asyncio.sleep(0.4)  # un humain rapide
            me = view["players"][my_seat]
            if view["must_flip"]:
                await ws.send(json.dumps({"action": "flip", "index": random.randrange(me["face_down_count"])}))
            elif view["playable_values"]:
                value = min(view["playable_values"])
                copies = len([c for c in (me["hand"] or []) if c["value"] == value])
                payload = {"action": "play", "value": value, "count": max(copies, 1)}
                if value == 7:
                    payload["direction"] = ">="
                await ws.send(json.dumps(payload))
                moves += 1


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8004")
    ap.add_argument("--tables", type=int, default=5)
    ap.add_argument("--bots", type=int, default=3)
    ap.add_argument("--difficulty", default="hard")
    args = ap.parse_args()
    ws_base = args.api.replace("https://", "wss://").replace("http://", "ws://")
    latencies: list[float] = []
    t0 = time.monotonic()
    await asyncio.gather(
        *(play_table(args.api, ws_base, i, args.bots, args.difficulty, latencies) for i in range(args.tables))
    )
    if latencies:
        lat = sorted(latencies)
        print(
            f"\n{args.tables} tables × {args.bots} bots {args.difficulty} : {len(lat)} coups de bot en "
            f"{time.monotonic() - t0:.0f}s ; réponse médiane {statistics.median(lat):.2f}s, "
            f"p90 {lat[int(len(lat) * 0.9)]:.2f}s, max {lat[-1]:.2f}s"
        )


if __name__ == "__main__":
    asyncio.run(main())
