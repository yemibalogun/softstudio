"""add products and waitlist subscribers

Additive only: creates two new tables and touches nothing that already
exists, so it is safe to run against the production database.

Revision ID: c7a41f9b2d10
Revises: ba3460b047bd
Create Date: 2026-09-20

"""
from alembic import op
import sqlalchemy as sa


revision = 'c7a41f9b2d10'
down_revision = 'ba3460b047bd'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'products',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('slug', sa.String(length=180), nullable=False),
        sa.Column('short_description', sa.String(length=280), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('image', sa.String(length=512), nullable=True),
        sa.Column('published', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('waitlist_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('featured', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cta_label', sa.String(length=80), nullable=True),
        sa.Column('cta_url', sa.String(length=512), nullable=True),
        sa.Column('meta_title', sa.String(length=180), nullable=True),
        sa.Column('meta_description', sa.String(length=300), nullable=True),
        sa.Column('og_image', sa.String(length=512), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug'),
    )
    op.create_index(op.f('ix_products_slug'), 'products', ['slug'], unique=True)
    op.create_index(op.f('ix_products_published'), 'products', ['published'], unique=False)
    op.create_index(op.f('ix_products_featured'), 'products', ['featured'], unique=False)

    op.create_table(
        'waitlist_subscribers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=True),
        sa.Column('source', sa.String(length=60), nullable=True),
        sa.Column('utm_medium', sa.String(length=60), nullable=True),
        sa.Column('utm_campaign', sa.String(length=120), nullable=True),
        sa.Column('utm_content', sa.String(length=120), nullable=True),
        sa.Column('ip_address', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        # One signup per email per product, enforced by the database.
        sa.UniqueConstraint('product_id', 'email', name='uq_waitlist_product_email'),
    )
    op.create_index(
        op.f('ix_waitlist_subscribers_product_id'), 'waitlist_subscribers', ['product_id'], unique=False
    )
    op.create_index(op.f('ix_waitlist_subscribers_email'), 'waitlist_subscribers', ['email'], unique=False)
    op.create_index(op.f('ix_waitlist_subscribers_source'), 'waitlist_subscribers', ['source'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_waitlist_subscribers_source'), table_name='waitlist_subscribers')
    op.drop_index(op.f('ix_waitlist_subscribers_email'), table_name='waitlist_subscribers')
    op.drop_index(op.f('ix_waitlist_subscribers_product_id'), table_name='waitlist_subscribers')
    op.drop_table('waitlist_subscribers')

    op.drop_index(op.f('ix_products_featured'), table_name='products')
    op.drop_index(op.f('ix_products_published'), table_name='products')
    op.drop_index(op.f('ix_products_slug'), table_name='products')
    op.drop_table('products')
