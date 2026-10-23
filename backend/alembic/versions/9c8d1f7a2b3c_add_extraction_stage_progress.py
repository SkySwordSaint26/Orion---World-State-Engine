"""add extraction stage progress

Revision ID: 9c8d1f7a2b3c
Revises: ef5362e51e02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9c8d1f7a2b3c"
down_revision: Union[str, None] = "ef5362e51e02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("processing_jobs", sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("processing_jobs", sa.Column("current_stage", sa.String(length=100), nullable=True))
    op.add_column("processing_jobs", sa.Column("current_chapter", sa.Integer(), nullable=True))
    op.alter_column("processing_jobs", "progress_percent", server_default=None)


def downgrade() -> None:
    op.drop_column("processing_jobs", "current_chapter")
    op.drop_column("processing_jobs", "current_stage")
    op.drop_column("processing_jobs", "progress_percent")
