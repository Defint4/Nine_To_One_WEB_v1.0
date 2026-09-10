"""players + player_game_stats

Revision ID: 0001
Revises:
Create Date: 2026-09-10

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "players",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("pseudo_key", sa.String(length=20), nullable=False),
        sa.Column("pseudo", sa.String(length=20), nullable=False),
        sa.Column("avatar", sa.String(length=40), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_players_pseudo_key"), "players", ["pseudo_key"], unique=True)

    op.create_table(
        "player_game_stats",
        sa.Column("player_id", sa.UUID(), nullable=False),
        sa.Column("game", sa.String(length=40), nullable=False),
        sa.Column("played", sa.Integer(), server_default="0", nullable=False),
        sa.Column("won", sa.Integer(), server_default="0", nullable=False),
        sa.Column("lost", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("player_id", "game"),
    )


def downgrade() -> None:
    op.drop_table("player_game_stats")
    op.drop_index(op.f("ix_players_pseudo_key"), table_name="players")
    op.drop_table("players")
