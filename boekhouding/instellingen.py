"""Instellingen, logo, CSV-export en back-up."""
import csv
import datetime as dt
import io

from flask import Blueprint, Response, abort, current_app, flash, redirect, render_template, request, send_file, url_for

from .archief import write_backup_zip
from .constants import DEFAULT_SETTINGS
from .db import available_years, get_db, settings
from .files import delete_file, send_stored_file, store_file
from .formatting import money_input
from .invoices import invoice_summaries

bp = Blueprint("instellingen", __name__)


@bp.route("/instellingen", methods=["GET", "POST"])
def instellingen():
    if request.method == "POST":
        for k in DEFAULT_SETTINGS:
            if k == "logo":
                continue
            if k in request.form:
                get_db().execute("UPDATE settings SET value=? WHERE key=?", (request.form[k].strip(), k))
        old_logo = settings().get("logo")
        logo = request.files.get("logo")
        new_logo = None
        if logo and logo.filename:
            try:
                new_logo = str(store_file(logo, {".png", ".jpg", ".jpeg"}))
            except ValueError:
                flash("Logo moet een PNG of JPG zijn.", "error")
        elif request.form.get("remove_logo"):
            new_logo = ""
        if new_logo is not None:
            get_db().execute("UPDATE settings SET value=? WHERE key='logo'", (new_logo,))
            delete_file(old_logo)
        get_db().commit()
        flash("Instellingen opgeslagen.", "ok")
        return redirect(url_for("instellingen.instellingen"))
    return render_template("instellingen.html", data_dir=str(current_app.config["DATA_DIR"]),
                           years=available_years())


@bp.route("/logo")
def logo():
    return send_stored_file(settings().get("logo"))


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
        for e in get_db().execute("SELECT e.*, f.name AS receipt_name FROM expenses e "
                                  "LEFT JOIN files f ON f.id = e.receipt_id "
                                  "WHERE e.date>=? AND e.date<? ORDER BY e.date, e.id", (ys, ye)):
            w.writerow([e["date"], e["supplier"], e["description"], e["category"], e["vat_type"],
                        e["vat_rate"], c2s(e["amount_excl_cents"]), c2s(e["vat_cents"]),
                        c2s(e["total_cents"]), e["receipt_name"] or ""])
    else:
        abort(404)
    data = "﻿" + buf.getvalue()  # BOM zodat Excel de tekens goed leest
    return Response(data, mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{kind}_{year}.csv"'})


@bp.route("/backup")
def backup():
    mem = io.BytesIO()
    write_backup_zip(mem)
    mem.seek(0)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    return send_file(mem, mimetype="application/zip", as_attachment=True,
                     download_name=f"boekhouding-backup-{stamp}.zip")
