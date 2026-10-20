"""add page views, error events, service subscriptions and payments

Additive only: four new tables, nothing existing is touched, so this is safe
to run against the live database.

Revision ID: a9d41c6e7b25
Revises: f1c3a8e5d2b7
Create Date: 2026-10-20

"""
from alembic import op
import sqlalchemy as sa


revision = 'a9d41c6e7b25'
down_revision = 'f1c3a8e5d2b7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'page_views',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('path', sa.String(length=255), nullable=False),
        sa.Column('status_code', sa.SmallInteger(), nullable=False, server_default='200'),
        sa.Column('source', sa.String(length=60), nullable=True),
        sa.Column('referrer_host', sa.String(length=120), nullable=True),
        sa.Column('device', sa.String(length=10), nullable=True),
        sa.Column('is_authenticated', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('visitor_hash', sa.String(length=64), nullable=True),
        sa.Column('product_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_page_views_path'), 'page_views', ['path'])
    op.create_index(op.f('ix_page_views_source'), 'page_views', ['source'])
    op.create_index(op.f('ix_page_views_visitor_hash'), 'page_views', ['visitor_hash'])
    op.create_index(op.f('ix_page_views_product_id'), 'page_views', ['product_id'])
    op.create_index(op.f('ix_page_views_created_at'), 'page_views', ['created_at'])
    # The dashboard's commonest query: "views in this window, grouped".
    op.create_index('ix_page_views_created_at_path', 'page_views', ['created_at', 'path'])

    op.create_table(
        'error_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('status_code', sa.SmallInteger(), nullable=True),
        sa.Column('path', sa.String(length=255), nullable=True),
        sa.Column('method', sa.String(length=10), nullable=True),
        sa.Column('message', sa.String(length=300), nullable=False),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.Column('fingerprint', sa.String(length=64), nullable=False),
        sa.Column('occurrences', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('first_seen', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_referrer', sa.String(length=255), nullable=True),
        sa.Column('resolved', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('fingerprint'),
    )
    op.create_index(op.f('ix_error_events_kind'), 'error_events', ['kind'])
    op.create_index(op.f('ix_error_events_fingerprint'), 'error_events', ['fingerprint'], unique=True)
    op.create_index(op.f('ix_error_events_last_seen'), 'error_events', ['last_seen'])
    op.create_index(op.f('ix_error_events_resolved'), 'error_events', ['resolved'])

    op.create_table(
        'service_subscriptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('vendor', sa.String(length=120), nullable=True),
        sa.Column('category', sa.String(length=20), nullable=False, server_default='other'),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False, server_default='0'),
        sa.Column('currency', sa.String(length=8), nullable=False, server_default='USD'),
        sa.Column('cycle', sa.String(length=12), nullable=False, server_default='monthly'),
        sa.Column('next_due_on', sa.Date(), nullable=True),
        sa.Column('auto_renew', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('manage_url', sa.String(length=512), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('last_paid_on', sa.Date(), nullable=True),
        sa.Column('reminder_stage_sent', sa.SmallInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_service_subscriptions_category'), 'service_subscriptions', ['category'])
    op.create_index(op.f('ix_service_subscriptions_next_due_on'), 'service_subscriptions', ['next_due_on'])
    op.create_index(op.f('ix_service_subscriptions_is_active'), 'service_subscriptions', ['is_active'])

    op.create_table(
        'service_payments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('subscription_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False, server_default='0'),
        sa.Column('currency', sa.String(length=8), nullable=False, server_default='USD'),
        sa.Column('paid_on', sa.Date(), nullable=False),
        sa.Column('note', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['subscription_id'], ['service_subscriptions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_service_payments_subscription_id'), 'service_payments', ['subscription_id'])
    op.create_index(op.f('ix_service_payments_paid_on'), 'service_payments', ['paid_on'])


def downgrade():
    op.drop_index(op.f('ix_service_payments_paid_on'), table_name='service_payments')
    op.drop_index(op.f('ix_service_payments_subscription_id'), table_name='service_payments')
    op.drop_table('service_payments')

    op.drop_index(op.f('ix_service_subscriptions_is_active'), table_name='service_subscriptions')
    op.drop_index(op.f('ix_service_subscriptions_next_due_on'), table_name='service_subscriptions')
    op.drop_index(op.f('ix_service_subscriptions_category'), table_name='service_subscriptions')
    op.drop_table('service_subscriptions')

    op.drop_index(op.f('ix_error_events_resolved'), table_name='error_events')
    op.drop_index(op.f('ix_error_events_last_seen'), table_name='error_events')
    op.drop_index(op.f('ix_error_events_fingerprint'), table_name='error_events')
    op.drop_index(op.f('ix_error_events_kind'), table_name='error_events')
    op.drop_table('error_events')

    op.drop_index('ix_page_views_created_at_path', table_name='page_views')
    op.drop_index(op.f('ix_page_views_created_at'), table_name='page_views')
    op.drop_index(op.f('ix_page_views_product_id'), table_name='page_views')
    op.drop_index(op.f('ix_page_views_visitor_hash'), table_name='page_views')
    op.drop_index(op.f('ix_page_views_source'), table_name='page_views')
    op.drop_index(op.f('ix_page_views_path'), table_name='page_views')
    op.drop_table('page_views')
