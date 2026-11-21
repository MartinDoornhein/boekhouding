"""Klanten beheren."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from .db import get_db

bp = Blueprint("klanten", __name__)

CUSTOMER_FIELDS = ["name", "contact", "email", "address", "postcode", "city", "country", "vat_id", "kvk"]


@bp.route("/klanten")
def klanten():
    rows = get_db().execute(
        """SELECT c.*, (SELECT COUNT(*) FROM invoices i WHERE i.customer_id=c.id) n
           FROM customers c ORDER BY c.name COLLATE NOCASE""").fetchall()
    return render_template("klanten.html", customers=rows)


@bp.route("/klanten/nieuw", methods=["GET", "POST"])
@bp.route("/klanten/<int:cid>", methods=["GET", "POST"])
def klant_bewerken(cid=None):
    cust = None
    if cid:
        cust = get_db().execute("SELECT * FROM customers WHERE id=?", (cid,)).fetchone() or abort(404)
    if request.method == "POST":
        vals = {f: request.form.get(f, "").strip() for f in CUSTOMER_FIELDS}
        if not vals["name"]:
            flash("Naam is verplicht.", "error")
            return render_template("klant_form.html", c=vals, cid=cid)
        if cid:
            get_db().execute(f"UPDATE customers SET {', '.join(f + '=?' for f in CUSTOMER_FIELDS)} WHERE id=?",
                         [vals[f] for f in CUSTOMER_FIELDS] + [cid])
        else:
            cur = get_db().execute(f"INSERT INTO customers ({', '.join(CUSTOMER_FIELDS)}) VALUES "
                               f"({', '.join('?' * len(CUSTOMER_FIELDS))})",
                               [vals[f] for f in CUSTOMER_FIELDS])
            cid = cur.lastrowid
        get_db().commit()
        flash("Klant opgeslagen.", "ok")
        nxt = request.args.get("next")
        if nxt == "factuur":
            return redirect(url_for("facturen.factuur_nieuw", klant=cid))
        return redirect(url_for("klanten.klanten"))
    return render_template("klant_form.html", c=cust or {"country": "Nederland"}, cid=cid)


@bp.post("/klanten/<int:cid>/verwijderen")
def klant_verwijderen(cid):
    n = get_db().execute("SELECT COUNT(*) n FROM invoices WHERE customer_id=?", (cid,)).fetchone()["n"]
    if n:
        flash("Deze klant heeft facturen en kan niet worden verwijderd.", "error")
    else:
        get_db().execute("DELETE FROM customers WHERE id=?", (cid,))
        get_db().commit()
        flash("Klant verwijderd.", "ok")
    return redirect(url_for("klanten.klanten"))
