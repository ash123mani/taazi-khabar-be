"""add_cached_questions_table

Revision ID: e7f2a4b3c1d0
Revises: d5e8f3a1b2c0
Create Date: 2026-06-07 16:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'e7f2a4b3c1d0'
down_revision: Union[str, None] = 'd5e8f3a1b2c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('cached_questions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('article_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('question_text', sa.Text(), nullable=False),
        sa.Column('options', postgresql.JSONB, nullable=False),
        sa.Column('correct_answer', sa.String(length=10), nullable=False),
        sa.Column('explanation', sa.Text(), nullable=True),
        sa.Column('difficulty', sa.String(length=10), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['article_id'], ['articles.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_cached_questions_article_id', 'cached_questions', ['article_id'])


def downgrade() -> None:
    op.drop_index('ix_cached_questions_article_id')
    op.drop_table('cached_questions')
