"""Eenvoudige boekhouding voor een eenmanszaak.

Facturen, kosten, btw-aangifte per kwartaal en jaaroverzicht.
Start met:  flask --app boekhouding run   (of: python -m boekhouding)
"""
import datetime as dt
import os
import secrets
from pathlib import Path

from flask import Flask, Response, current_app, request

from .constants import EXPENSE_VAT_TYPES, VAT_MODES
from .formatting import TEMPLATE_FILTERS

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def create_app(test_config=None):
    # De instance-map (buiten het package) bevat de lokale data: database (incl. bonnen en logo) en secret.
    data_dir = Path(os.environ.get("BOEKHOUDING_DATA", DEFAULT_DATA_DIR)).resolve()
    if test_config and "DATA_DIR" in test_config:
        data_dir = Path(test_config["DATA_DIR"]).resolve()
    app = Flask(__name__, instance_path=str(data_dir), instance_relative_config=True)
    app.config.from_mapping(
        DATA_DIR=data_dir,
        DATABASE=data_dir / "boekhouding.db",
        PASSWORD=os.environ.get("BOEKHOUDING_WACHTWOORD", ""),
        MAX_CONTENT_LENGTH=25 * 1024 * 1024,
    )
    if test_config is None:
        # Optioneel: eigen instellingen in <data>/config.py
        app.config.from_pyfile("config.py", silent=True)
    else:
        app.config.from_mapping({**test_config, "DATA_DIR": data_dir})

    app.config["DATA_DIR"].mkdir(parents=True, exist_ok=True)
    if not app.config.get("SECRET_KEY"):  # Flask zet standaard SECRET_KEY=None
        app.config["SECRET_KEY"] = _secret_key(app.config["DATA_DIR"])

    from . import archief, db
    db.init_app(app)
    archief.init_app(app)
    with app.app_context():
        db.init_db()

    app.jinja_env.filters.update(TEMPLATE_FILTERS)
    app.context_processor(_inject)
    app.before_request(_check_password)

    from . import facturen, instellingen, klanten, kosten, rapportage
    for module in (rapportage, klanten, facturen, kosten, instellingen):
        app.register_blueprint(module.bp)

    return app


def _secret_key(data_dir):
    key_file = data_dir / ".secret"
    if not key_file.exists():
        key_file.write_text(secrets.token_hex(32))
    return key_file.read_text().strip()


def _inject():
    from .db import settings
    return {"s": settings(), "VAT_MODES": VAT_MODES, "EXPENSE_VAT_TYPES": EXPENSE_VAT_TYPES,
            "today": dt.date.today().isoformat()}


def _check_password():
    password = current_app.config["PASSWORD"]
    if not password:
        return None
    auth = request.authorization
    if auth and secrets.compare_digest(auth.password or "", password):
        return None
    return Response("Inloggen vereist", 401, {"WWW-Authenticate": 'Basic realm="Boekhouding"'})
