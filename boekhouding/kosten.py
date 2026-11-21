"""Kosten en bonnetjes."""
import datetime as dt
from decimal import Decimal

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from .constants import ALLOWED_RECEIPTS, DEFAULT_CATEGORIES, EXPENSE_VAT_TYPES
from .db import available_years, get_db
from .files import delete_file, send_stored_file, store_file
from .formatting import money_input, parse_date, parse_money, quarter_range, rhu

bp = Blueprint("kosten", __name__)


def categories():
    used = [r["category"] for r in get_db().execute(
        "SELECT DISTINCT category FROM expenses WHERE category IS NOT NULL AND category != ''")]
    return DEFAULT_CATEGORIES + sorted(c for c in used if c not in DEFAULT_CATEGORIES)


def calc_expense(total, vat_type, rate, override):
    if vat_type == "nl":
        vat = override if override is not None else rhu(Decimal(total) * rate / (100 + rate))
        return total - vat, vat
    if vat_type == "geen":
        return total, 0
    # verlegd: het factuurbedrag is excl. btw; je berekent zelf de btw (verschuldigd én aftrekbaar)
    vat = override if override is not None else rhu(Decimal(total) * rate / 100)
    return total, vat


@bp.route("/kosten")
def kosten():
    year = request.args.get("jaar", type=int) or dt.date.today().year
    q = request.args.get("kwartaal", type=int)
    cat = request.args.get("categorie", "")
    start, end = quarter_range(year, q) if q in (1, 2, 3, 4) else (f"{year}-01-01", f"{year + 1}-01-01")
    sql, params = "SELECT * FROM expenses WHERE date >= ? AND date < ?", [start, end]
    if cat:
        sql += " AND category = ?"
        params.append(cat)
    rows = get_db().execute(sql + " ORDER BY date DESC, id DESC", params).fetchall()
    sums = {k: sum(r[k] for r in rows) for k in ("amount_excl_cents", "vat_cents", "total_cents")}
    return render_template("kosten.html", expenses=rows, sums=sums, year=year, q=q, cat=cat,
                           years=available_years(), categories=categories())


@bp.route("/kosten/nieuw", methods=["GET", "POST"])
@bp.route("/kosten/<int:eid>", methods=["GET", "POST"])
def kosten_bewerken(eid=None):
    exp = None
    if eid:
        exp = get_db().execute("SELECT * FROM expenses WHERE id=?", (eid,)).fetchone() or abort(404)
    if request.method == "POST":
        f = request.form
        try:
            date = parse_date(f.get("date"))
            if not date:
                raise ValueError("Vul een geldige datum in.")
            total = parse_money(f.get("total"))
            if total is None:
                raise ValueError("Vul het bedrag in.")
            vat_type = f.get("vat_type") if f.get("vat_type") in EXPENSE_VAT_TYPES else "nl"
            rate = int(f.get("vat_rate")) if f.get("vat_rate") in ("21", "9", "0") else 21
            override = parse_money(f.get("vat_override"))
            excl, vat = calc_expense(total, vat_type, rate, override)
            vals = (date, f.get("supplier", "").strip(), f.get("description", "").strip(),
                    f.get("category", "").strip() or "Overig", vat_type, rate, total, excl, vat)
            if eid:
                get_db().execute("UPDATE expenses SET date=?, supplier=?, description=?, category=?, vat_type=?, "
                             "vat_rate=?, total_cents=?, amount_excl_cents=?, vat_cents=? WHERE id=?",
                             vals + (eid,))
            else:
                eid = get_db().execute("INSERT INTO expenses (date, supplier, description, category, vat_type, "
                                   "vat_rate, total_cents, amount_excl_cents, vat_cents) "
                                   "VALUES (?,?,?,?,?,?,?,?,?)", vals).lastrowid
            file = request.files.get("receipt")
            old_receipt = exp["receipt_id"] if exp else None
            if file and file.filename:
                get_db().execute("UPDATE expenses SET receipt_id=? WHERE id=?",
                                 (store_file(file, ALLOWED_RECEIPTS), eid))
                delete_file(old_receipt)
            elif f.get("remove_receipt") and old_receipt:
                get_db().execute("UPDATE expenses SET receipt_id=NULL WHERE id=?", (eid,))
                delete_file(old_receipt)
            get_db().commit()
        except ValueError as e:
            get_db().rollback()
            flash(str(e), "error")
            vals = {k: f.get(k, "") for k in ("date", "supplier", "description", "category", "vat_type",
                                              "vat_rate", "total", "vat_override")}
            vals["receipt_id"] = exp["receipt_id"] if exp else None
            return render_template("kosten_form.html", e=vals, eid=exp["id"] if exp else None,
                                   categories=categories())
        flash("Kosten opgeslagen.", "ok")
        if f.get("again"):
            return redirect(url_for("kosten.kosten_bewerken"))
        return redirect(url_for("kosten.kosten", jaar=date[:4]))
    if exp:
        _, auto_vat = calc_expense(exp["total_cents"], exp["vat_type"], exp["vat_rate"], None)
        vals = {"date": exp["date"], "supplier": exp["supplier"] or "", "description": exp["description"] or "",
                "category": exp["category"] or "", "vat_type": exp["vat_type"], "vat_rate": str(exp["vat_rate"]),
                "total": money_input(exp["total_cents"]),
                "vat_override": money_input(exp["vat_cents"]) if exp["vat_cents"] != auto_vat else "",
                "receipt_id": exp["receipt_id"], "amount_excl_cents": exp["amount_excl_cents"],
                "vat_cents": exp["vat_cents"]}
    else:
        vals = {"date": dt.date.today().isoformat(), "vat_type": "nl", "vat_rate": "21"}
    return render_template("kosten_form.html", e=vals, eid=eid, categories=categories())


@bp.post("/kosten/<int:eid>/verwijderen")
def kosten_verwijderen(eid):
    exp = get_db().execute("SELECT * FROM expenses WHERE id=?", (eid,)).fetchone() or abort(404)
    get_db().execute("DELETE FROM expenses WHERE id=?", (eid,))
    delete_file(exp["receipt_id"])
    get_db().commit()
    flash("Kosten verwijderd.", "ok")
    return redirect(url_for("kosten.kosten", jaar=exp["date"][:4]))


@bp.route("/kosten/<int:eid>/bon")
def kosten_bon(eid):
    exp = get_db().execute("SELECT receipt_id FROM expenses WHERE id=?", (eid,)).fetchone()
    return send_stored_file(exp["receipt_id"] if exp else None)
