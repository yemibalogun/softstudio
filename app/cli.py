import getpass

import click
from flask import Flask


def register_cli_commands(app: Flask) -> None:

    @app.cli.command("seed")
    def seed():
        """Populate the database with development sample data."""
        from app.extensions import db
        from app.models import (
            Role, Project, Technology, Service, Course, CourseCategory,
            CourseSection, Lesson, Testimonial,
        )
        from app.auth.services import get_or_create_default_role

        get_or_create_default_role("student")
        admin_role = Role.query.filter_by(name="admin").first()
        if not admin_role:
            admin_role = Role()
            admin_role.name = "admin"
            admin_role.description = "Full administrative access"

            db.session.add(admin_role)
            db.session.flush()

        flask_tech, _ = _get_or_create(Technology, name="Flask", slug="flask")
        postgres_tech, _ = _get_or_create(Technology, name="PostgreSQL", slug="postgresql")

        project, created = _get_or_create(
            Project,
            slug="sample-saas-dashboard",
            defaults=dict(
                title="Sample SaaS Dashboard",
                short_description="A metrics dashboard built for a logistics client.",
                description="A full example project seeded for local development.",
                category="Web Application",
                status="live",
                featured=True,
                published=True,
            ),
        )
        if created:
            project.technologies.extend([flask_tech, postgres_tech])

        _get_or_create(
            Service,
            slug="custom-software-development",
            defaults=dict(
                title="Custom Software Development",
                summary="Business applications, portals, dashboards and internal systems.",
                published=True,
                display_order=1,
            ),
        )

        category, _ = _get_or_create(
            CourseCategory, slug="flask", defaults=dict(name="Flask", description="Flask courses")
        )
        course, created = _get_or_create(
            Course,
            slug="flask-production-applications",
            defaults=dict(
                title="Flask Production Applications",
                short_description="Build and ship real-world Flask apps.",
                description="A sample seeded course for local development.",
                price=15000,
                currency="NGN",
                difficulty="intermediate",
                published=True,
                featured=True,
                category_id=category.id,
            ),
        )
        if created:
            section = CourseSection()
            section.course_id = course.id
            section.title = "Getting Started"
            section.display_order = 1
            db.session.add(section)
            db.session.flush()

            lesson = Lesson()
            lesson.section_id = section.id
            lesson.title = "Introduction"
            lesson.slug = "introduction"
            lesson.is_free_preview = True
            lesson.display_order = 1

            db.session.add(lesson)

        _get_or_create(
            Testimonial,
            author_name="Sample Client",
            defaults=dict(
                author_title="Founder, Example Co.",
                quote="Great work on our platform.",
                approved=True,
                featured=True,
            ),
        )

        db.session.commit()
        click.echo("Seed data created.")

    @app.cli.command("create-admin")
    @click.option("--email", prompt=True)
    @click.option("--full-name", prompt="Full name")
    def create_admin(email, full_name):
        """Create (or promote) an administrator account."""
        from app.extensions import db
        from app.models import User, Role

        password = getpass.getpass("Password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            click.echo("Passwords do not match.", err=True)
            raise SystemExit(1)
        if len(password) < 10:
            click.echo("Password must be at least 10 characters.", err=True)
            raise SystemExit(1)

        admin_role = Role.query.filter_by(name="admin").first()
        if not admin_role:
            admin_role = Role()
            admin_role.name = "admin"
            admin_role.description = "Full administrative access"

            db.session.add(admin_role)
            db.session.flush()

        user = User.query.filter_by(email=email.lower()).first()
        if user:
            user.role_id = admin_role.id
            click.echo(f"Promoted existing user {email} to admin.")
        else:
            user = User()
            user.email = email.lower()
            user.full_name = full_name
            user.role_id = admin_role.id
            user.email_verified = True
            user.set_password(password)
            db.session.add(user)
            click.echo(f"Created admin user {email}.")

        db.session.commit()

    @app.cli.command("verify-config")
    def verify_config():
        """Sanity-check that critical environment variables are set."""
        import os

        checks = {
            "SECRET_KEY": os.environ.get("SECRET_KEY"),
            "DATABASE_URL": os.environ.get("DATABASE_URL"),
            "MAIL_SERVER": os.environ.get("MAIL_SERVER"),
            "PAYMENT_PROVIDER": os.environ.get("PAYMENT_PROVIDER"),
            "SITE_URL": os.environ.get("SITE_URL"),
        }
        missing = [k for k, v in checks.items() if not v]
        for k, v in checks.items():
            status = "OK" if v else "MISSING"
            click.echo(f"{k}: {status}")
        if missing:
            click.echo(f"\n{len(missing)} variable(s) missing.", err=True)
            raise SystemExit(1)
        click.echo("\nAll critical configuration present.")

    @app.cli.command("send-renewal-reminders")
    def send_renewal_reminders():
        """
        Email upcoming service renewals. Run daily from cron:

            0 8 * * *  cd /srv/app && flask send-renewal-reminders

        Each stage (14, 7, 1 days out, and the overdue nudge) is sent once
        per due date, tracked by reminder_stage_sent, so running the command
        more than once a day is harmless.
        """
        from datetime import date

        from app import emails
        from app.extensions import db
        from app.models import ServiceSubscription

        STAGES = (14, 7, 1, 0)
        sent = 0

        subscriptions = ServiceSubscription.query.filter(
            ServiceSubscription.is_active.is_(True),
            ServiceSubscription.next_due_on.isnot(None),
        ).all()

        for subscription in subscriptions:
            days_left = (subscription.next_due_on - date.today()).days
            if days_left > STAGES[0]:
                continue  # still far off; nothing to say yet
            # The stage this reminder belongs to: the tightest one reached.
            # Smaller means closer, and -1 is the single overdue nudge.
            stage = -1 if days_left < 0 else min(s for s in STAGES if s >= days_left)
            already = subscription.reminder_stage_sent
            if already is not None and already <= stage:
                continue

            if emails.send_renewal_reminder(subscription, days_left):
                subscription.reminder_stage_sent = stage
                sent += 1
                click.echo(f"reminded: {subscription.name} ({days_left} days)")
            else:
                click.echo(f"FAILED to email about {subscription.name}", err=True)

        db.session.commit()
        click.echo(f"{sent} reminder(s) sent.")

    @app.cli.command("prune-analytics")
    @click.option("--days", default=180, show_default=True, help="Keep page views newer than this.")
    def prune_analytics(days):
        """Drop old raw page views. The dashboard's ranges only look back 30 days."""
        from app.analytics import prune_page_views

        deleted = prune_page_views(days)
        click.echo(f"{deleted} page view(s) removed.")


def _get_or_create(model, defaults=None, **kwargs):
    from app.extensions import db

    instance = model.query.filter_by(**kwargs).first()
    if instance:
        return instance, False
    params = dict(kwargs)
    params.update(defaults or {})
    instance = model(**params)
    db.session.add(instance)
    db.session.flush()
    return instance, True
