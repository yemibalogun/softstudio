"""add gated product downloads

Additive only: new nullable columns on products (plus one boolean with a
server default, so existing rows are filled in place), and one new table.
Nothing existing is changed or dropped, so it is safe to run against the
production database.

Revision ID: e4b2d9a7c316
Revises: c7a41f9b2d10
Create Date: 2026-10-12

"""
from alembic import op
import sqlalchemy as sa


revision = 'e4b2d9a7c316'
down_revision = 'c7a41f9b2d10'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('products', sa.Column('download_file', sa.String(length=255), nullable=True))
    op.add_column('products', sa.Column('download_filename', sa.String(length=255), nullable=True))
    op.add_column('products', sa.Column('download_size', sa.BigInteger(), nullable=True))
    op.add_column('products', sa.Column('download_sha256', sa.String(length=64), nullable=True))
    op.add_column('products', sa.Column('download_version', sa.String(length=40), nullable=True))
    op.add_column('products', sa.Column('download_updated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        'products',
        sa.Column('download_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        'download_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('link_sent_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('link_uses', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('email_delivered', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('request_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('download_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('first_downloaded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_downloaded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('source', sa.String(length=60), nullable=True),
        sa.Column('utm_medium', sa.String(length=60), nullable=True),
        sa.Column('utm_campaign', sa.String(length=120), nullable=True),
        sa.Column('utm_content', sa.String(length=120), nullable=True),
        sa.Column('ip_address', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        # One lead per email per product; asking again reuses the row.
        sa.UniqueConstraint('product_id', 'email', name='uq_download_product_email'),
    )
    op.create_index(
        op.f('ix_download_requests_product_id'), 'download_requests', ['product_id'], unique=False
    )
    op.create_index(op.f('ix_download_requests_email'), 'download_requests', ['email'], unique=False)
    op.create_index(
        op.f('ix_download_requests_token_hash'), 'download_requests', ['token_hash'], unique=True
    )
    op.create_index(op.f('ix_download_requests_source'), 'download_requests', ['source'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_download_requests_source'), table_name='download_requests')
    op.drop_index(op.f('ix_download_requests_token_hash'), table_name='download_requests')
    op.drop_index(op.f('ix_download_requests_email'), table_name='download_requests')
    op.drop_index(op.f('ix_download_requests_product_id'), table_name='download_requests')
    op.drop_table('download_requests')

    op.drop_column('products', 'download_enabled')
    op.drop_column('products', 'download_updated_at')
    op.drop_column('products', 'download_version')
    op.drop_column('products', 'download_sha256')
    op.drop_column('products', 'download_size')
    op.drop_column('products', 'download_filename')
    op.drop_column('products', 'download_file')
