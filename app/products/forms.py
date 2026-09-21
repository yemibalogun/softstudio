from flask_wtf import FlaskForm
from wtforms import HiddenField, StringField
from wtforms.validators import DataRequired, Email, Length, Optional


def _normalized_email(value):
    """Addresses are pasted with stray spaces and capitals; store one form."""
    return value.strip().lower() if isinstance(value, str) else value


def _stripped(value):
    return value.strip() if isinstance(value, str) else value


class WaitlistForm(FlaskForm):
    """Join-the-waitlist form: email required, everything else optional."""

    email = StringField(
        "Email address",
        filters=[_normalized_email],
        validators=[DataRequired(), Email(), Length(max=255)],
    )
    name = StringField("Name", filters=[_stripped], validators=[Optional(), Length(max=120)])

    # Attribution carried through the page so a share link's campaign
    # parameters survive the POST. Client-supplied, so treated as untrusted
    # labels: normalized and length-capped before storage, never trusted to
    # identify the product (that comes from the URL slug).
    utm_source = HiddenField(validators=[Optional(), Length(max=100)])
    utm_medium = HiddenField(validators=[Optional(), Length(max=100)])
    utm_campaign = HiddenField(validators=[Optional(), Length(max=200)])
    utm_content = HiddenField(validators=[Optional(), Length(max=200)])

    # Honeypot: hidden from real users, same approach as the contact form.
    website = StringField("Website", validators=[Optional()])
