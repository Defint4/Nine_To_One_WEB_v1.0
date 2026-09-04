from pydantic import BaseModel

from app.rooms.manager import Room


class RoomOut(BaseModel):
    code: str


def open_room_summary(room: Room) -> dict:
    """Résumé public d'un lobby rejoignable (liste des parties)."""
    return {
        "code": room.code,
        "players": [{"pseudo": s.pseudo, "avatar": s.avatar} for s in room.seats],
        "seats_taken": len(room.seats),
        "seats_max": 5,
    }
