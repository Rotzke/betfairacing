#!/usr/bin/python3
"""Flask forms collection."""
from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField
from wtforms.validators import DataRequired


class LoginForm(FlaskForm):
    """Login page login form."""

    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
