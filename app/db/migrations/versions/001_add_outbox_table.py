"""add outbox table for transactional outbox pattern

Revision ID: add_outbox_table
Revises: 
Create Date: 2026-02-04 14:04:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_outbox_table'
down_revision: Union[str, None] = None
head_label: str = 'head'
depends_on: Union[str, None] = None


def upgrade() -> None:
    # Create outbox table
    op.create_table(
        'outbox',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('exchange_name', sa.String(length=255), nullable=False),
        sa.Column('message_type', sa.String(length=255), nullable=False),
        sa.Column('routing_key', sa.String(length=255), nullable=False),
        sa.Column('payload', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index(op.f('ix_outbox_id'), 'outbox', ['id'], unique=False)
    op.create_index(op.f('ix_outbox_exchange_name'), 'outbox', ['exchange_name'], unique=False)
    op.create_index(op.f('ix_outbox_created_at'), 'outbox', ['created_at'], unique=False)


def downgrade() -> None:
    # Drop indexes
    op.drop_index(op.f('ix_outbox_created_at'), table_name='outbox')
    op.drop_index(op.f('ix_outbox_exchange_name'), table_name='outbox')
    op.drop_index(op.f('ix_outbox_id'), table_name='outbox')
    
    # Drop table
    op.drop_table('outbox')
