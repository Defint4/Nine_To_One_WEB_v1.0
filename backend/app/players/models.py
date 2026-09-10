import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.mixins import IdMixin, TimestampMixin


class Player(IdMixin, TimestampMixin, Base):
    __tablename__ = "players"

    # pseudo_key : version minuscule, clé d'unicité insensible à la casse ;
    # pseudo garde la casse choisie par le joueur pour l'affichage.
    pseudo_key: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    pseudo: Mapped[str] = mapped_column(String(20))
    avatar: Mapped[str] = mapped_column(String(40))

    # Chargées avec le profil : le hub et les fiches joueur les affichent toujours.
    stats: Mapped[list["PlayerGameStats"]] = relationship(
        back_populates="player", lazy="selectin", cascade="all, delete-orphan"
    )


class PlayerGameStats(Base):
    """Bilan d'un joueur sur un jeu (une ligne par jeu joué)."""

    __tablename__ = "player_game_stats"

    player_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), primary_key=True
    )
    game: Mapped[str] = mapped_column(String(40), primary_key=True)  # GameSpec.slug
    played: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    won: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    lost: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    player: Mapped[Player] = relationship(back_populates="stats")
