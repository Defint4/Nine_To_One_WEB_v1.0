from pydantic import BaseModel, Field

from app.rooms.manager import Room


class CreateRoomRequest(BaseModel):
    game: str = Field(pattern=r"^[a-z0-9\-]{1,40}$")


class RoomOut(BaseModel):
    code: str
    game: str


class RoomStatusOut(RoomOut):
    """Ce qu'il faut pour savoir si une table se reprend : son état, et si le joueur y
    est encore assis."""

    status: str
    seated: bool


def open_room_summary(room: Room) -> dict:
    """Résumé public d'un lobby rejoignable (liste des tables)."""
    return {
        "code": room.code,
        "game": room.game,
        "players": [{"pseudo": s.pseudo, "avatar": s.avatar} for s in room.seats],
        "seats_taken": len(room.seats),
        "seats_max": room.spec.max_players,
    }
