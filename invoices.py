"""Facturen: berekeningen en opvragen."""
import datetime as dt
from decimal import Decimal

from flask import abort

from database import db, settings
from formatting import rhu


def line_amount(line) -> int:
    return rhu(Decimal(str(line["quantity"])) * int(line["unit_price_cents"]))


def invoice_totals(lines, vat_mode):
    groups = {}
    for ln in lines:
        rate = int(ln["vat_rate"]) if vat_mode == "normaal" else 0
        groups[rate] = groups.get(rate, 0) + line_amount(ln)
    vat = {r: rhu(Decimal(b) * r / 100) for r, b in groups.items()}
    rows = [(r, groups[r], vat[r]) for r in sorted(groups, reverse=True)]
    subtotal = sum(groups.values())
    vat_total = sum(vat.values())
    return {"groups": rows, "subtotal": subtotal, "vat": vat_total, "total": subtotal + vat_total}


def load_invoice(inv_id):
    inv = db().execute("SELECT * FROM invoices WHERE id=?", (inv_id,)).fetchone()
    if inv is None:
        abort(404)
    cust = db().execute("SELECT * FROM customers WHERE id=?", (inv["customer_id"],)).fetchone()
    lines = db().execute("SELECT * FROM invoice_lines WHERE invoice_id=? ORDER BY position, id",
                         (inv_id,)).fetchall()
    return inv, cust, lines


def next_invoice_number(year):
    prefix = settings().get("factuur_prefix", "")
    base = f"{prefix}{year}-"
    rows = db().execute("SELECT number FROM invoices WHERE number LIKE ?", (base + "%",)).fetchall()
    seq = 0
    for r in rows:
        try:
            seq = max(seq, int(r["number"][len(base):]))
        except ValueError:
            pass
    return f"{base}{seq + 1:03d}"


def invoice_summaries(where="1=1", params=()):
    rows = db().execute(
        f"""SELECT i.*, c.name AS cname, c.vat_id AS cvat, c.country AS ccountry
            FROM invoices i JOIN customers c ON c.id = i.customer_id
            WHERE {where} ORDER BY i.date DESC, i.number DESC, i.id DESC""", params).fetchall()
    out = []
    for r in rows:
        lines = db().execute("SELECT * FROM invoice_lines WHERE invoice_id=?", (r["id"],)).fetchall()
        d = dict(r)
        d.update(invoice_totals(lines, r["vat_mode"]))
        d["overdue"] = r["status"] == "open" and (r["due_date"] or "9999") < dt.date.today().isoformat()
        out.append(d)
    return out
