"""SQLite-verbinding, schema en instellingen."""
import datetime as dt
import sqlite3

import click
from flask import current_app, g
from flask.cli import with_appcontext

from .constants import DEFAULT_SETTINGS


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        # Aanbevolen voor Litestream: wachten i.p.v. 'database is locked' tijdens een checkpoint.
        g.db.execute("PRAGMA busy_timeout = 5000")
        g.db.execute("PRAGMA synchronous = NORMAL")
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    con = g.pop("db", None)
    if con is not None:
        con.close()


def init_db():
    """Maak ontbrekende tabellen en standaardinstellingen aan (bestaande data blijft staan)."""
    con = get_db()
    con.execute("PRAGMA journal_mode = WAL")  # vereist door Litestream
    with current_app.open_resource("schema.sql") as f:
        con.executescript(f.read().decode("utf8"))
    con.executemany("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", DEFAULT_SETTINGS.items())
    _migrate_files_into_db(con)
    con.commit()


def _migrate_files_into_db(con):
    """Eenmalig: bonnen en logo van schijf (oude versie) naar de files-tabel.

    De oude bestanden op schijf blijven staan; die kun je na controle zelf verwijderen.
    """
    from .files import insert_file

    data_dir = current_app.config["DATA_DIR"]
    cols = {r["name"] for r in con.execute("PRAGMA table_info(expenses)")}
    if "receipt_id" not in cols:
        con.execute("ALTER TABLE expenses ADD COLUMN receipt_id INTEGER REFERENCES files(id)")
    if "receipt_path" in cols:
        upload_dir = (data_dir / "bonnen").resolve()
        rows = con.execute("SELECT id, receipt_path FROM expenses "
                           "WHERE receipt_path IS NOT NULL AND receipt_id IS NULL").fetchall()
        for r in rows:
            p = (upload_dir / r["receipt_path"]).resolve()
            if upload_dir in p.parents and p.is_file():
                fid = insert_file(p.name, p.read_bytes())
                con.execute("UPDATE expenses SET receipt_id=?, receipt_path=NULL WHERE id=?", (fid, r["id"]))

    logo = con.execute("SELECT value FROM settings WHERE key='logo'").fetchone()["value"] or ""
    if logo and not logo.isdigit():  # oude versie: bestandsnaam i.p.v. file-id
        p = data_dir / logo
        new = str(insert_file(p.name, p.read_bytes())) if p.is_file() else ""
        con.execute("UPDATE settings SET value=? WHERE key='logo'", (new,))


@click.command("init-db")
@with_appcontext
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
