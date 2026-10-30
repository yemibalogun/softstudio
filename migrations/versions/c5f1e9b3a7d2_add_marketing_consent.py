"""add marketing consent to download requests and waitlist subscribers

Additive only: three nullable-or-defaulted columns on each table. Existing
sign-ups get marketing_consent = false - nobody who signed up before the
opt-in box existed agreed to marketing email - so it is safe to run against
the production database.

Revision ID: c5f1e9b3a7d2
Revises: b3e7c2a91f04
Create Date: 2026-10-30

"""
from alembic import op
import sqlalchemy as sa


revision = 'c5f1e9b3a7d2'
down_revision = 'b3e7c2a91f04'
branch_labels = None
depends_on = None

TABLES = ('download_requests', 'waitlist_subscribers')


def upgrade():
    for table in TABLES:
        op.add_column(table, sa.Column('marketing_consent', sa.Boolean(), nullable=False,
                                       server_default=sa.false()))
        op.add_column(table, sa.Column('consent_at', sa.DateTime(timezone=True), nullable=True))
        op.add_column(table, sa.Column('unsubscribed_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    for table in TABLES:
        op.drop_column(table, 'unsubscribed_at')
        op.drop_column(table, 'consent_at')
        op.drop_column(table, 'marketing_consent')
