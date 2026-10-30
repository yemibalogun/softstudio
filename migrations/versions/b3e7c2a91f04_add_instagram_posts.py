"""add instagram posts

Additive only: one new table for the /reels page. Nothing existing is
touched, so it is safe to run against the production database.

Revision ID: b3e7c2a91f04
Revises: a9d41c6e7b25
Create Date: 2026-10-30

"""
from alembic import op
import sqlalchemy as sa


revision = 'b3e7c2a91f04'
down_revision = 'a9d41c6e7b25'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'instagram_posts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shortcode', sa.String(length=40), nullable=False),
        sa.Column('kind', sa.String(length=10), nullable=False),
        sa.Column('title', sa.String(length=160), nullable=True),
        sa.Column('caption', sa.Text(), nullable=True),
        sa.Column('cover_image', sa.String(length=512), nullable=True),
        sa.Column('posted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('published', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('source', sa.String(length=20), nullable=False, server_default='admin'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_instagram_posts_shortcode'), 'instagram_posts', ['shortcode'], unique=True)
    op.create_index(op.f('ix_instagram_posts_published'), 'instagram_posts', ['published'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_instagram_posts_published'), table_name='instagram_posts')
    op.drop_index(op.f('ix_instagram_posts_shortcode'), table_name='instagram_posts')
    op.drop_table('instagram_posts')
