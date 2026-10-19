"""add product landing page fields

Additive only: four new columns on products, one of them a boolean with a
server default so existing rows are filled in place. Nothing existing is
changed or dropped, so it is safe to run against the production database.

Revision ID: f1c3a8e5d2b7
Revises: e4b2d9a7c316
Create Date: 2026-10-19

"""
from alembic import op
import sqlalchemy as sa


revision = 'f1c3a8e5d2b7'
down_revision = 'e4b2d9a7c316'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'products',
        sa.Column('landing_page', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column('products', sa.Column('landing_headline', sa.String(length=200), nullable=True))
    op.add_column('products', sa.Column('landing_points', sa.Text(), nullable=True))
    op.add_column('products', sa.Column('landing_button_label', sa.String(length=80), nullable=True))


def downgrade():
    op.drop_column('products', 'landing_button_label')
    op.drop_column('products', 'landing_points')
    op.drop_column('products', 'landing_headline')
    op.drop_column('products', 'landing_page')
