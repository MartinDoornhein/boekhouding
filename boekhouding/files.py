"""Bestanden (bonnen, logo) als BLOB in de database, zodat Litestream alles repliceert."""
import io
import mimetypes
from pathlib import Path

from flask import abort, send_file
from werkzeug.utils import secure_filename

from .db import get_db


def store_file(upload, allowed_exts):
    """Sla een geüpload bestand op en geef het id terug. Commit gebeurt door de aanroeper."""
    ext = Path(upload.filename).suffix.lower()
    if ext not in allowed_exts:
        raise ValueError(f"Bestandstype {ext or '?'} niet toegestaan ({', '.join(sorted(allowed_exts))}).")
    data = upload.read()
    name = secure_filename(upload.filename) or f"bestand{ext}"
    return insert_file(name, data, upload.mimetype)


def insert_file(name, data, mimetype=None):
    mimetype = mimetype or mimetypes.guess_type(name)[0] or "application/octet-stream"
    return get_db().execute("INSERT INTO files (name, mimetype, size, data) VALUES (?,?,?,?)",
                            (name, mimetype, len(data), data)).lastrowid


def delete_file(file_id):
    if file_id:
        get_db().execute("DELETE FROM files WHERE id=?", (file_id,))


def file_data(file_id):
    if not file_id:
        return None
    row = get_db().execute("SELECT data FROM files WHERE id=?", (file_id,)).fetchone()
    return row["data"] if row else None


def send_stored_file(file_id, as_attachment=False):
    row = get_db().execute("SELECT name, mimetype, data FROM files WHERE id=?", (file_id,)).fetchone() \
        if file_id else None
    if row is None:
        abort(404)
    return send_file(io.BytesIO(row["data"]), mimetype=row["mimetype"], download_name=row["name"],
                     as_attachment=as_attachment)
