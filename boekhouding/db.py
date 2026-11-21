"""SQLite-verbinding, schema en instellingen."""
import datetime as dt
import sqlite3

import click
from flask import current_app, g

from .constants import DEFAULT_SETTINGS


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    con = g.pop("db", None)
    if con is not None:
        con.close()


def init_db():
    """Maak ontbrekende tabellen en standaardinstellingen aan (bestaande data blijft staan)."""
    con = get_db()
    with current_app.open_resource("schema.sql") as f:
        con.executescript(f.read().decode("utf8"))
    con.executemany("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", DEFAULT_SETTINGS.items())
    con.commit()


@click.command("init-db")
def init_db_command():
    """Maak de database aan of werk het schema bij."""
    init_db()
    click.echo(f"Database klaar: {current_app.config['DATABASE']}")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)


def settings():
    if "settings" not in g:
        g.settings = {r["key"]: r["value"] or "" for r in get_db().execute("SELECT * FROM settings")}
    return g.settings


def available_years():
    rows = get_db().execute(
        "SELECT substr(date,1,4) y FROM invoices UNION SELECT substr(date,1,4) FROM expenses"
    ).fetchall()
    years = {int(r["y"]) for r in rows if r["y"]}
    years.add(dt.date.today().year)
    return sorted(years, reverse=True)
