"""Facturen: aanmaken, bewerken, definitief maken, crediteren en PDF."""
import datetime as dt
import io
from urllib.parse import quote

from flask import Blueprint, current_app, flash, redirect, render_template, request, send_file, url_for

from .constants import VAT_MODE_TEXT, VAT_MODES
from .db import available_years, get_db, settings
from .formatting import eur, fmt_date, fmt_qty, money_input, parse_date, parse_money, parse_qty
from .invoices import invoice_summaries, invoice_totals, line_amount, load_invoice, next_invoice_number

bp = Blueprint("facturen", __name__)


@bp.route("/facturen")
def facturen():
    year = request.args.get("jaar", type=int) or dt.date.today().year
    status = request.args.get("status", "")
    where, params = "i.date >= ? AND i.date < ?", [f"{year}-01-01", f"{year + 1}-01-01"]
    if status:
        where += " AND i.status = ?"
        params.append(status)
    rows = invoice_summaries(where, params)
    return render_template("facturen.html", invoices=rows, year=year, status=status,
                           years=available_years())


def _save_invoice_form(inv_id=None):
    f = request.form
    try:
        customer_id = int(f.get("customer_id", ""))
    except ValueError:
        raise ValueError("Kies een klant.")
    date = parse_date(f.get("date")) or dt.date.today().isoformat()
    vat_mode = f.get("vat_mode") if f.get("vat_mode") in VAT_MODES else "normaal"
    lines = []
    for i, (desc, qty, price, rate) in enumerate(zip(f.getlist("description"), f.getlist("quantity"),
                                                     f.getlist("unit_price"), f.getlist("vat_rate"))):
        desc = desc.strip()
        if not desc and not price.strip():
            continue
        if not desc:
            raise ValueError("Elke factuurregel heeft een omschrijving nodig.")
        rate = int(rate) if rate in ("21", "9", "0") else 21
        lines.append((i, desc, float(parse_qty(qty)), parse_money(price, 0), rate))
    if not lines:
        raise ValueError("Voeg minstens één factuurregel toe.")
    terms = int(settings().get("betaaltermijn") or 30)
    due = (dt.date.fromisoformat(date) + dt.timedelta(days=terms)).isoformat()
    vals = (customer_id, date, due, f.get("period", "").strip(), vat_mode, f.get("notes", "").strip())
    if inv_id:
        get_db().execute("UPDATE invoices SET customer_id=?, date=?, due_date=?, period=?, vat_mode=?, notes=? "
                     "WHERE id=?", vals + (inv_id,))
        get_db().execute("DELETE FROM invoice_lines WHERE invoice_id=?", (inv_id,))
    else:
        inv_id = get_db().execute("INSERT INTO invoices (customer_id, date, due_date, period, vat_mode, notes) "
                              "VALUES (?,?,?,?,?,?)", vals).lastrowid
    get_db().executemany("INSERT INTO invoice_lines (invoice_id, position, description, quantity, "
                     "unit_price_cents, vat_rate) VALUES (?,?,?,?,?,?)",
                     [(inv_id,) + ln for ln in lines])
    get_db().commit()
    return inv_id


def _form_lines():
    f = request.form
    return [{"description": d, "quantity": q, "unit_price": p, "vat_rate": r}
            for d, q, p, r in zip(f.getlist("description"), f.getlist("quantity"),
                                  f.getlist("unit_price"), f.getlist("vat_rate"))]


@bp.route("/facturen/nieuw", methods=["GET", "POST"])
def factuur_nieuw():
    customers = get_db().execute("SELECT * FROM customers ORDER BY name COLLATE NOCASE").fetchall()
    if request.method == "POST":
        try:
            inv_id = _save_invoice_form()
            flash("Concept opgeslagen. Controleer en maak de factuur definitief.", "ok")
            return redirect(url_for("facturen.factuur", inv_id=inv_id))
        except ValueError as e:
            flash(str(e), "error")
            return render_template("factuur_form.html", inv=request.form, lines=_form_lines(),
                                   customers=customers, from_form=True)
    inv = {"customer_id": request.args.get("klant", type=int), "vat_mode": "normaal",
           "date": dt.date.today().isoformat()}
    return render_template("factuur_form.html", inv=inv, lines=[], customers=customers)


@bp.route("/facturen/<int:inv_id>/bewerken", methods=["GET", "POST"])
def factuur_bewerken(inv_id):
    inv, cust, lines = load_invoice(inv_id)
    if inv["status"] != "concept":
        flash("Een definitieve factuur kun je niet meer wijzigen. Maak een creditfactuur.", "error")
        return redirect(url_for("facturen.factuur", inv_id=inv_id))
    customers = get_db().execute("SELECT * FROM customers ORDER BY name COLLATE NOCASE").fetchall()
    if request.method == "POST":
        try:
            _save_invoice_form(inv_id)
            flash("Concept bijgewerkt.", "ok")
            return redirect(url_for("facturen.factuur", inv_id=inv_id))
        except ValueError as e:
            flash(str(e), "error")
            return render_template("factuur_form.html", inv=request.form, lines=_form_lines(),
                                   customers=customers, inv_id=inv_id, from_form=True)
    form_lines = [{"description": l["description"], "quantity": fmt_qty(l["quantity"]),
                   "unit_price": money_input(l["unit_price_cents"]), "vat_rate": str(l["vat_rate"])}
                  for l in lines]
    return render_template("factuur_form.html", inv=inv, lines=form_lines, customers=customers,
                           inv_id=inv_id)


@bp.route("/facturen/<int:inv_id>")
def factuur(inv_id):
    inv, cust, lines = load_invoice(inv_id)
    totals = invoice_totals(lines, inv["vat_mode"])
    credit_of = None
    if inv["credit_of"]:
        credit_of = get_db().execute("SELECT id, number FROM invoices WHERE id=?", (inv["credit_of"],)).fetchone()
    credits = get_db().execute("SELECT id, number, status FROM invoices WHERE credit_of=?", (inv_id,)).fetchall()
    mailto = None
    if inv["status"] != "concept":
        s = settings()
        ctx = {"nummer": inv["number"], "bedrag": eur(totals["total"]),
               "vervaldatum": fmt_date(inv["due_date"]), "bedrijfsnaam": s.get("bedrijfsnaam", ""),
               "naam": s.get("naam", ""), "klant": cust["contact"] or cust["name"]}
        try:
            subject = s.get("mail_onderwerp", "").format(**ctx)
            body = s.get("mail_tekst", "").format(**ctx)
        except (KeyError, IndexError, ValueError):
            subject, body = f"Factuur {inv['number']}", ""
        mailto = f"mailto:{quote(cust['email'] or '')}?subject={quote(subject)}&body={quote(body)}"
    return render_template("factuur.html", inv=inv, c=cust, lines=lines, t=totals,
                           line_amount=line_amount, credit_of=credit_of, credits=credits,
                           mailto=mailto, vat_text=VAT_MODE_TEXT.get(inv["vat_mode"]))


@bp.post("/facturen/<int:inv_id>/definitief")
def factuur_definitief(inv_id):
    inv, cust, lines = load_invoice(inv_id)
    if inv["status"] != "concept":
        return redirect(url_for("facturen.factuur", inv_id=inv_id))
    s = settings()
    missing = [n for k, n in [("bedrijfsnaam", "bedrijfsnaam"), ("kvk", "KvK-nummer"),
                              ("btw_id", "btw-id"), ("iban", "IBAN"), ("adres", "adres")] if not s.get(k)]
    if missing:
        flash("Vul eerst je bedrijfsgegevens aan bij Instellingen: " + ", ".join(missing) + ".", "error")
        return redirect(url_for("facturen.factuur", inv_id=inv_id))
    if inv["vat_mode"] == "eu_b2b" and not cust["vat_id"]:
        flash("Bij btw verleggen naar een EU-klant is het btw-id van de klant verplicht.", "error")
        return redirect(url_for("facturen.factuur", inv_id=inv_id))
    year = inv["date"][:4]
    number = next_invoice_number(year)
    get_db().execute("UPDATE invoices SET number=?, status='open' WHERE id=?", (number, inv_id))
    if inv["credit_of"]:
        orig, _, orig_lines = load_invoice(inv["credit_of"])
        own = invoice_totals(lines, inv["vat_mode"])["total"]
        if orig["status"] == "open" and invoice_totals(orig_lines, orig["vat_mode"])["total"] + own == 0:
            today = dt.date.today().isoformat()
            get_db().execute("UPDATE invoices SET status='betaald', paid_date=? WHERE id IN (?, ?)",
                         (today, inv_id, orig["id"]))
            flash("Factuur en creditnota heffen elkaar op en zijn als afgehandeld gemarkeerd.", "ok")
    get_db().commit()
    flash(f"Factuur {number} is definitief.", "ok")
    return redirect(url_for("facturen.factuur", inv_id=inv_id))


@bp.post("/facturen/<int:inv_id>/betaald")
def factuur_betaald(inv_id):
    paid = parse_date(request.form.get("paid_date")) or dt.date.today().isoformat()
    get_db().execute("UPDATE invoices SET status='betaald', paid_date=? WHERE id=? AND status='open'",
                 (paid, inv_id))
    get_db().commit()
    flash("Gemarkeerd als betaald.", "ok")
    return redirect(request.form.get("back") or url_for("facturen.factuur", inv_id=inv_id))


@bp.post("/facturen/<int:inv_id>/heropenen")
def factuur_heropenen(inv_id):
    get_db().execute("UPDATE invoices SET status='open', paid_date=NULL WHERE id=? AND status='betaald'",
                 (inv_id,))
    get_db().commit()
    return redirect(url_for("facturen.factuur", inv_id=inv_id))


@bp.post("/facturen/<int:inv_id>/verwijderen")
def factuur_verwijderen(inv_id):
    inv, _, _ = load_invoice(inv_id)
    if inv["status"] != "concept":
        flash("Alleen concepten kunnen worden verwijderd.", "error")
        return redirect(url_for("facturen.factuur", inv_id=inv_id))
    get_db().execute("DELETE FROM invoices WHERE id=?", (inv_id,))
    get_db().commit()
    flash("Concept verwijderd.", "ok")
    return redirect(url_for("facturen.facturen"))


@bp.post("/facturen/<int:inv_id>/crediteren")
def factuur_crediteren(inv_id):
    inv, cust, lines = load_invoice(inv_id)
    if inv["status"] == "concept":
        return redirect(url_for("facturen.factuur", inv_id=inv_id))
    today = dt.date.today().isoformat()
    new_id = get_db().execute(
        "INSERT INTO invoices (customer_id, date, due_date, period, vat_mode, notes, credit_of) "
        "VALUES (?,?,?,?,?,?,?)",
        (inv["customer_id"], today, today, inv["period"], inv["vat_mode"],
         f"Creditering van factuur {inv['number']}.", inv_id)).lastrowid
    get_db().executemany(
        "INSERT INTO invoice_lines (invoice_id, position, description, quantity, unit_price_cents, vat_rate) "
        "VALUES (?,?,?,?,?,?)",
        [(new_id, l["position"], l["description"], -l["quantity"], l["unit_price_cents"], l["vat_rate"])
         for l in lines])
    get_db().commit()
    flash("Creditfactuur als concept aangemaakt. Pas eventueel aan en maak definitief.", "ok")
    return redirect(url_for("facturen.factuur", inv_id=new_id))


@bp.route("/facturen/<int:inv_id>/pdf")
def factuur_pdf(inv_id):
    from .pdf import build_invoice_pdf
    inv, cust, lines = load_invoice(inv_id)
    totals = invoice_totals(lines, inv["vat_mode"])
    credit_of = None
    if inv["credit_of"]:
        r = get_db().execute("SELECT number FROM invoices WHERE id=?", (inv["credit_of"],)).fetchone()
        credit_of = r["number"] if r else None
    s = settings()
    logo = current_app.config["DATA_DIR"] / s["logo"] if s.get("logo") else None
    data = build_invoice_pdf(inv, cust, lines, totals, s, logo if logo and logo.exists() else None,
                             helpers={"eur": eur, "datum": fmt_date, "aantal": fmt_qty,
                                      "line_amount": line_amount},
                             vat_text=VAT_MODE_TEXT.get(inv["vat_mode"]), credit_of=credit_of)
    name = f"Factuur {inv['number']}.pdf" if inv["number"] else f"Concept factuur {inv_id}.pdf"
    if inv["credit_of"] and inv["number"]:
        name = f"Creditfactuur {inv['number']}.pdf"
    return send_file(io.BytesIO(data), mimetype="application/pdf", download_name=name,
                     as_attachment=request.args.get("download") == "1")
