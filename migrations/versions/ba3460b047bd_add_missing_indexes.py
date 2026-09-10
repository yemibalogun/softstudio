"""Add missing indexes on filtered/joined columns

Revision ID: ba3460b047bd
Revises: ce9923051953
Create Date: 2026-09-04 01:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ba3460b047bd'
down_revision = 'ce9923051953'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_users_is_active'), ['is_active'], unique=False)

    with op.batch_alter_table('user_sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_sessions_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_user_sessions_revoked_at'), ['revoked_at'], unique=False)

    with op.batch_alter_table('project_inquiries', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_project_inquiries_status'), ['status'], unique=False)

    with op.batch_alter_table('enrollments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_enrollments_status'), ['status'], unique=False)

    with op.batch_alter_table('purchases', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_purchases_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_purchases_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_projects_featured'), ['featured'], unique=False)
        batch_op.create_index(batch_op.f('ix_projects_published'), ['published'], unique=False)

    with op.batch_alter_table('project_images', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_project_images_project_id'), ['project_id'], unique=False)

    with op.batch_alter_table('courses', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_courses_published'), ['published'], unique=False)
        batch_op.create_index(batch_op.f('ix_courses_featured'), ['featured'], unique=False)
        batch_op.create_index(batch_op.f('ix_courses_category_id'), ['category_id'], unique=False)

    with op.batch_alter_table('course_sections', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_course_sections_course_id'), ['course_id'], unique=False)

    with op.batch_alter_table('lesson_progress', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_lesson_progress_lesson_id'), ['lesson_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_lesson_progress_completed'), ['completed'], unique=False)

    with op.batch_alter_table('oauth_identities', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_oauth_identities_provider'), ['provider'], unique=False)
        batch_op.create_index(batch_op.f('ix_oauth_identities_provider_user_id'), ['provider_user_id'], unique=False)

    with op.batch_alter_table('blog_posts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_blog_posts_published'), ['published'], unique=False)
        batch_op.create_index(batch_op.f('ix_blog_posts_category_id'), ['category_id'], unique=False)

    with op.batch_alter_table('services', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_services_published'), ['published'], unique=False)

    with op.batch_alter_table('testimonials', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_testimonials_approved'), ['approved'], unique=False)
        batch_op.create_index(batch_op.f('ix_testimonials_featured'), ['featured'], unique=False)


def downgrade():
    with op.batch_alter_table('testimonials', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_testimonials_featured'))
        batch_op.drop_index(batch_op.f('ix_testimonials_approved'))

    with op.batch_alter_table('services', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_services_published'))

    with op.batch_alter_table('blog_posts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_blog_posts_category_id'))
        batch_op.drop_index(batch_op.f('ix_blog_posts_published'))

    with op.batch_alter_table('oauth_identities', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_oauth_identities_provider_user_id'))
        batch_op.drop_index(batch_op.f('ix_oauth_identities_provider'))

    with op.batch_alter_table('lesson_progress', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_lesson_progress_completed'))
        batch_op.drop_index(batch_op.f('ix_lesson_progress_lesson_id'))

    with op.batch_alter_table('course_sections', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_course_sections_course_id'))

    with op.batch_alter_table('courses', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_courses_category_id'))
        batch_op.drop_index(batch_op.f('ix_courses_featured'))
        batch_op.drop_index(batch_op.f('ix_courses_published'))

    with op.batch_alter_table('project_images', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_project_images_project_id'))

    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_projects_published'))
        batch_op.drop_index(batch_op.f('ix_projects_featured'))

    with op.batch_alter_table('purchases', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_purchases_user_id'))
        batch_op.drop_index(batch_op.f('ix_purchases_status'))

    with op.batch_alter_table('enrollments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_enrollments_status'))

    with op.batch_alter_table('project_inquiries', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_project_inquiries_status'))

    with op.batch_alter_table('user_sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_sessions_revoked_at'))
        batch_op.drop_index(batch_op.f('ix_user_sessions_user_id'))

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_is_active'))
