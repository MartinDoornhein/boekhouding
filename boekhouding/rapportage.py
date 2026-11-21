"""Overzicht (dashboard), btw-aangifte en jaaroverzicht."""
import datetime as dt

from flask import Blueprint, render_template, request

from .btw_aangifte import compute_btw
from .constants import INVESTMENT_CAT
from .db import available_years, get_db, settings
from .formatting import current_quarter, quarter_range
from .invoices import invoice_summaries

bp = Blueprint("rapportage", __name__)


@bp.route("/")
def dashboard():
    year, q = current_quarter()
    ys, ye = f"{year}-01-01", f"{year + 1}-01-01"
    inv = invoice_summaries("i.status != 'concept' AND i.date >= ? AND i.date < ?", (ys, ye))
    omzet = sum(i["subtotal"] for i in inv)
    kosten = get_db().execute(
        "SELECT COALESCE(SUM(amount_excl_cents),0) s FROM expenses WHERE date>=? AND date<? AND category != ?",
        (ys, ye, INVESTMENT_CAT)).fetchone()["s"]
    qs, qe = quarter_range(year, q)
    btw = compute_btw(qs, qe)
    open_inv = invoice_summaries("i.status = 'open'")
    concepts = invoice_summaries("i.status = 'concept'")
    recent = get_db().execute("SELECT * FROM expenses ORDER BY date DESC, id DESC LIMIT 8").fetchall()
    missing = [k for k in ("bedrijfsnaam", "kvk", "btw_id", "iban") if not settings().get(k)]
    return render_template("dashboard.html", year=year, q=q, omzet=omzet, kosten=kosten,
                           btw=btw, open_inv=open_inv, concepts=concepts, recent=recent,
                           missing=missing)


@bp.route("/btw")
def btw():
    cy, cq = current_quarter()
    year = request.args.get("jaar", type=int) or cy
    q = request.args.get("kwartaal", type=int) or cq
    start, end = quarter_range(year, q)
    data = compute_btw(start, end)
    # Aangifte en betaling uiterlijk de laatste dag van de maand na het kwartaal
    first_next = dt.date.fromisoformat(end)
    last_day = (first_next.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
    concepts = get_db().execute("SELECT COUNT(*) n FROM invoices WHERE status='concept' AND date>=? AND date<?",
                            (start, end)).fetchone()["n"]
    return render_template("btw.html", d=data, year=year, q=q, years=available_years(),
                           deadline=last_day.isoformat(), concepts=concepts)


@bp.route("/jaar")
def jaar():
    year = request.args.get("jaar", type=int) or dt.date.today().year
    ys, ye = f"{year}-01-01", f"{year + 1}-01-01"
    inv = invoice_summaries("i.status != 'concept' AND i.date >= ? AND i.date < ?", (ys, ye))
    omzet = sum(i["subtotal"] for i in inv)
    btw_gefactureerd = sum(i["vat"] for i in inv)
    cats = get_db().execute(
        "SELECT category, COUNT(*) n, SUM(amount_excl_cents) excl, SUM(vat_cents) vat FROM expenses "
        "WHERE date>=? AND date<? AND category != ? GROUP BY category ORDER BY excl DESC",
        (ys, ye, INVESTMENT_CAT)).fetchall()
    kosten_tot = sum(c["excl"] for c in cats)
    investments = get_db().execute("SELECT * FROM expenses WHERE date>=? AND date<? AND category=? ORDER BY date",
                               (ys, ye, INVESTMENT_CAT)).fetchall()
    quarters = []
    for q in range(1, 5):
        d = compute_btw(*quarter_range(year, q))
        quarters.append({"q": q, "owed": d["owed"], "voor": d["voorbelasting"], "saldo": d["saldo"],
                         "saldo_r": d["saldo_r"]})
    debiteuren = [i for i in invoice_summaries("i.status != 'concept' AND i.date < ? AND "
                                               "(i.paid_date IS NULL OR i.paid_date >= ?)", (ye, ye))]
    return render_template("jaar.html", year=year, years=available_years(), omzet=omzet,
                           btw_gefactureerd=btw_gefactureerd, cats=cats, kosten=kosten_tot,
                           investments=investments, winst=omzet - kosten_tot, quarters=quarters,
                           n_inv=len(inv), debiteuren=debiteuren,
                           debiteuren_tot=sum(d["total"] for d in debiteuren))
