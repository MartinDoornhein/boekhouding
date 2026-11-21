"""Back-up/archief als zip: consistente database-snapshot plus alle bonnen als losse bestanden.

De losse bonnen maken het archief ook zonder deze app leesbaar (bewaarplicht 7 jaar).
"""
import datetime as dt
import sqlite3
import tempfile
import zipfile
from pathlib import Path

import click
from flask import current_app
from flask.cli import with_appcontext
from werkzeug.utils import secure_filename


def write_backup_zip(target):
    """Schrijf een back-up-zip naar `target` (pad of file-object)."""
    with tempfile.TemporaryDirectory() as tmp:
        snap = Path(tmp) / "boekhouding.db"
        src = sqlite3.connect(current_app.config["DATABASE"])
        dst = sqlite3.connect(snap)
        src.backup(dst)  # consistent, ook terwijl de app/Litestream draait
        src.close()
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(snap, "boekhouding.db")
            rows = dst.execute(
                "SELECT e.id, e.date, f.name, f.data FROM expenses e JOIN files f ON f.id = e.receipt_id "
                "ORDER BY e.date, e.id")
            for exp_id, date, name, data in rows:
                z.writestr(f"bonnen/{date[:4]}/{exp_id:05d}_{secure_filename(name) or 'bon'}", data)
        dst.close()


@click.command("archive")
@with_appcontext
@click.option("-o", "--output", type=click.Path(dir_okay=False, writable=True),
              help="Doelbestand (standaard: boekhouding-archief-<datum>.zip in de huidige map).")
def archive_command(output):
    """Maak een archief-zip (database + bonnen), bijv. eens per jaar voor de bewaarplicht."""
    output = output or f"boekhouding-archief-{dt.date.today().isoformat()}.zip"
    write_backup_zip(output)
    click.echo(output)


def init_app(app):
    app.cli.add_command(archive_command)
