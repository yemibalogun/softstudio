from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField
from wtforms.validators import DataRequired, Email, Length, Optional, Length as MaxLen


class ProjectInquiryForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=120)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    company = StringField("Company", validators=[Optional(), Length(max=160)])
    phone = StringField("Phone", validators=[Optional(), Length(max=40)])

    project_type = SelectField(
        "Project type",
        choices=[
            ("web_app", "Custom Web Application"),
            ("automation", "Business Automation"),
            ("integration", "API / System Integration"),
            ("ai", "AI Application"),
            ("consulting", "Consulting"),
            ("other", "Other"),
        ],
        validators=[DataRequired()],
    )
    project_description = TextAreaField(
        "Project description", validators=[DataRequired(), MaxLen(max=4000)]
    )
    current_process = TextAreaField("Current process", validators=[Optional(), MaxLen(max=4000)])
    desired_outcome = TextAreaField("Desired outcome", validators=[Optional(), MaxLen(max=4000)])
    budget_range = StringField("Budget range", validators=[Optional(), Length(max=60)])
    timeline = StringField("Timeline", validators=[Optional(), Length(max=60)])
    referral_source = StringField("How did you hear about us?", validators=[Optional(), Length(max=120)])

    # Honeypot field: real users never see/fill this (hidden via CSS).
    # Any non-empty value marks the submission as spam server-side.
    website = StringField("Website", validators=[Optional()])
