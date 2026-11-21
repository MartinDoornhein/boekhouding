"""Instellingen, logo, CSV-export en back-up."""
import csv
import datetime as dt
import io
import sqlite3
import tempfile
import zipfile
from pathlib import Path

from flask import Blueprint, Response, abort, current_app, flash, redirect, render_template, request, send_file, url_for

from .constants import DEFAULT_SETTINGS
from .db import available_years, get_db, settings
from .formatting import money_input
from .invoices import invoice_summaries

bp = Blueprint("instellingen", __name__)


@bp.route("/instellingen", methods=["GET", "POST"])
def instellingen():
    data_dir = current_app.config["DATA_DIR"]
    if request.method == "POST":
        for k in DEFAULT_SETTINGS:
            if k == "logo":
                continue
            if k in request.form:
                get_db().execute("UPDATE settings SET value=? WHERE key=?", (request.form[k].strip(), k))
        logo = request.files.get("logo")
        if logo and logo.filename:
            ext = Path(logo.filename).suffix.lower()
            if ext not in (".png", ".jpg", ".jpeg"):
                flash("Logo moet een PNG of JPG zijn.", "error")
            else:
                for old in data_dir.glob("logo.*"):
                    old.unlink()
                logo.save(data_dir / f"logo{ext}")
                get_db().execute("UPDATE settings SET value=? WHERE key='logo'", (f"logo{ext}",))
        if request.form.get("remove_logo"):
            for old in data_dir.glob("logo.*"):
                old.unlink()
            get_db().execute("UPDATE settings SET value='' WHERE key='logo'")
        get_db().commit()
        flash("Instellingen opgeslagen.", "ok")
        return redirect(url_for("instellingen.instellingen"))
    return render_template("instellingen.html", data_dir=str(data_dir), years=available_years())


@bp.route("/logo")
def logo():
    s = settings()
    data_dir = current_app.config["DATA_DIR"]
    p = data_dir / s["logo"] if s.get("logo") else None
    if not p or not p.is_file():
        abort(404)
    return send_file(p)


@bp.route("/export/<kind>.csv")
def export(kind):
    year = request.args.get("jaar", type=int) or dt.date.today().year
    ys, ye = f"{year}-01-01", f"{year + 1}-01-01"
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    c2s = money_input

    if kind == "facturen":
        w.writerow(["Factuurnummer", "Datum", "Vervaldatum", "Klant", "Btw-id klant", "Status",
                    "Btw-situatie", "Excl. btw", "Btw", "Totaal", "Betaald op", "Creditering van"])
        for i in sorted(invoice_summaries("i.status != 'concept' AND i.date>=? AND i.date<?", (ys, ye)),
                        key=lambda x: x["number"]):
            orig = ""
            if i["credit_of"]:
                r = get_db().execute("SELECT number FROM invoices WHERE id=?", (i["credit_of"],)).fetchone()
                orig = r["number"] if r else ""
            w.writerow([i["number"], i["date"], i["due_date"], i["cname"], i["cvat"] or "", i["status"],
                        i["vat_mode"], c2s(i["subtotal"]), c2s(i["vat"]), c2s(i["total"]),
                        i["paid_date"] or "", orig])
    elif kind == "kosten":
        w.writerow(["Datum", "Leverancier", "Omschrijving", "Categorie", "Btw-soort", "Tarief",
                    "Excl. btw", "Btw", "Totaal", "Bon"])
        for e in get_db().execute("SELECT * FROM expenses WHERE date>=? AND date<? ORDER BY date, id", (ys, ye)):
            w.writerow([e["date"], e["supplier"], e["description"], e["category"], e["vat_type"],
                        e["vat_rate"], c2s(e["amount_excl_cents"]), c2s(e["vat_cents"]),
                        c2s(e["total_cents"]), e["receipt_path"] or ""])
    else:
        abort(404)
    data = "﻿" + buf.getvalue()  # BOM zodat Excel de tekens goed leest
    return Response(data, mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{kind}_{year}.csv"'})


@bp.route("/backup")
def backup():
    data_dir = current_app.config["DATA_DIR"]
    with tempfile.TemporaryDirectory() as tmp:
        snap = Path(tmp) / "boekhouding.db"
        src = sqlite3.connect(current_app.config["DATABASE"])
        dst = sqlite3.connect(snap)
        src.backup(dst)
        dst.close()
        src.close()
        mem = io.BytesIO()
        with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(snap, "boekhouding.db")
            for p in data_dir.rglob("*"):
                if p.is_file() and p.name not in ("boekhouding.db", ".secret") and not p.name.endswith(
                        ("-wal", "-shm", "-journal")):
                    z.write(p, p.relative_to(data_dir).as_posix())
        mem.seek(0)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    return send_file(mem, mimetype="application/zip", as_attachment=True,
                     download_name=f"boekhouding-backup-{stamp}.zip")
