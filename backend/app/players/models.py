from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.mixins import IdMixin, TimestampMixin


class Player(IdMixin, TimestampMixin, Base):
    __tablename__ = "players"

    # pseudo_key : version minuscule, clé d'unicité insensible à la casse ;
    # pseudo garde la casse choisie par le joueur pour l'affichage.
    pseudo_key: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    pseudo: Mapped[str] = mapped_column(String(20))
    avatar: Mapped[str] = mapped_column(String(40))

    games_played: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    games_won: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # 1er sorti
    games_lost: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # dernier
