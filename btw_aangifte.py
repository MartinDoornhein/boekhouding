"""Btw-aangifte: rubrieken berekenen over een periode."""
from database import db
from invoices import invoice_summaries

RUBRIEKEN = [
    ("1a", "Leveringen/diensten belast met hoog tarief"),
    ("1b", "Leveringen/diensten belast met laag tarief"),
    ("1e", "Leveringen/diensten belast met 0% of niet bij u belast"),
    ("3b", "Leveringen naar of diensten in landen binnen de EU"),
    ("4a", "Leveringen/diensten uit landen buiten de EU"),
    ("4b", "Leveringen/diensten uit landen binnen de EU"),
]


def down(c):  # hele euro's, afronden in jouw voordeel (omlaag)
    return int(c / 100) if c < 0 else c // 100


def up(c):  # hele euro's, naar boven (voorbelasting)
    return -down(-c)


def compute_btw(start, end):
    R = {k: {"base": 0, "vat": 0} for k, _ in RUBRIEKEN}
    icp = {}
    invoices = invoice_summaries("i.status != 'concept' AND i.date >= ? AND i.date < ?", (start, end))
    for inv in invoices:
        mode = inv["vat_mode"]
        if mode == "normaal":
            for rate, base, vat in inv["groups"]:
                key = {21: "1a", 9: "1b"}.get(rate, "1e")
                R[key]["base"] += base
                R[key]["vat"] += vat
        elif mode == "eu_b2b":
            R["3b"]["base"] += inv["subtotal"]
            k = (inv["cvat"] or "— btw-id ontbreekt —", inv["cname"], inv["ccountry"] or "")
            icp[k] = icp.get(k, 0) + inv["subtotal"]
        else:
            R["1e"]["base"] += inv["subtotal"]

    expenses = db().execute("SELECT * FROM expenses WHERE date >= ? AND date < ? ORDER BY date",
                            (start, end)).fetchall()
    voorbelasting = 0
    for e in expenses:
        if e["vat_type"] == "nl":
            voorbelasting += e["vat_cents"]
        elif e["vat_type"] in ("eu_verlegd", "buiten_eu_verlegd"):
            key = "4b" if e["vat_type"] == "eu_verlegd" else "4a"
            R[key]["base"] += e["amount_excl_cents"]
            R[key]["vat"] += e["vat_cents"]
            voorbelasting += e["vat_cents"]

    owed = sum(R[k]["vat"] for k in ("1a", "1b", "4a", "4b"))
    rows = []
    for k, label in RUBRIEKEN:
        has_vat = k in ("1a", "1b", "4a", "4b")
        rows.append({"code": k, "label": label, "base": R[k]["base"],
                     "vat": R[k]["vat"] if has_vat else None,
                     "base_r": down(R[k]["base"]),
                     "vat_r": down(R[k]["vat"]) if has_vat else None})
    owed_r = sum(r["vat_r"] for r in rows if r["vat_r"] is not None)
    return {
        "rows": rows, "owed": owed, "owed_r": owed_r,
        "voorbelasting": voorbelasting, "voorbelasting_r": up(voorbelasting),
        "saldo": owed - voorbelasting, "saldo_r": owed_r - up(voorbelasting),
        "icp": [{"vat_id": k[0], "name": k[1], "country": k[2], "amount": v} for k, v in icp.items()],
        "invoices": sorted(invoices, key=lambda x: (x["date"], x["number"] or "")),
        "expenses": expenses,
    }
