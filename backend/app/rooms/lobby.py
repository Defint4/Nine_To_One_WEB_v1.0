"""Liste des tables ouvertes en direct : un WebSocket par écran d'accueil de jeu.

Sur téléphone en PWA, personne ne rafraîchit : une table créée doit apparaître chez
les autres à l'instant. Chaque accueil de jeu ouvre `WS /api/rooms/live?game=<slug>`
et reçoit la liste complète à chaque changement (création, arrivée, départ, démarrage,
suppression). Aucune authentification : la liste est déjà publique en REST.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from fastapi import WebSocket, WebSocketDisconnect

from app.rooms.manager import manager
from app.rooms.schemas import open_room_summary

logger = logging.getLogger(__name__)

_watchers: dict[str, set[WebSocket]] = defaultdict(set)


def _payload(game: str) -> dict:
    return {"type": "rooms", "rooms": [open_room_summary(r) for r in manager.open_rooms(game)]}


async def watch(websocket: WebSocket, game: str) -> None:
    """Tient la connexion d'un accueil de jeu ouverte jusqu'à son départ."""
    await websocket.accept()
    _watchers[game].add(websocket)
    try:
        await websocket.send_json(_payload(game))
        while True:
            # Le client n'a rien à dire ; on attend juste sa déconnexion.
            await websocket.receive_text()
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        _watchers[game].discard(websocket)


async def notify(game: str) -> None:
    """À appeler après tout changement d'une table en lobby de ce jeu."""
    sockets = _watchers.get(game)
    if not sockets:
        return
    payload = _payload(game)
    for socket in list(sockets):
        try:
            await socket.send_json(payload)
        except Exception:
            sockets.discard(socket)
