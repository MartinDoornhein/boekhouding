"""Eenvoudige boekhouding voor een eenmanszaak.

Facturen, kosten, btw-aangifte per kwartaal en jaaroverzicht.
Start met:  python app.py   en open http://127.0.0.1:5000
"""
import csv
import io
import os
import secrets
import sqlite3
import tempfile
import zipfile
import datetime as dt
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from urllib.parse import quote

from flask import (Flask, Response, abort, flash, g, redirect, render_template,
                   request, send_file, url_for)
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("BOEKHOUDING_DATA", BASE_DIR / "data")).resolve()
DB_PATH = DATA_DIR / "boekhouding.db"
UPLOAD_DIR = DATA_DIR / "bonnen"
PASSWORD = os.environ.get("BOEKHOUDING_WACHTWOORD", "")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

# --------------------------------------------------------------------------
# Constanten
# --------------------------------------------------------------------------
VAT_MODES = {
    "normaal": "Normaal – Nederlandse btw",
    "verlegd_nl": "Btw verlegd (binnenland)",
    "eu_b2b": "Dienst aan ondernemer in andere EU-lidstaat (btw verlegd)",
    "buiten_eu": "Klant buiten de EU (niet in NL belast)",
}
VAT_MODE_TEXT = {
    "verlegd_nl": "Btw verlegd.",
    "eu_b2b": "Btw verlegd / VAT reverse charge (art. 196 Richtlijn 2006/112/EG).",
    "buiten_eu": "Niet in Nederland belast / Not subject to Dutch VAT.",
}
EXPENSE_VAT_TYPES = {
    "nl": "Nederlandse btw (aftrekbaar)",
    "geen": "Geen of niet-aftrekbare btw",
    "eu_verlegd": "Verlegd – leverancier in andere EU-lidstaat",
    "buiten_eu_verlegd": "Verlegd – leverancier buiten de EU",
}
INVESTMENT_CAT = "Investering (≥ € 450, afschrijven)"
DEFAULT_CATEGORIES = [
    "Software & abonnementen", "Hardware (< € 450)", "Kantoorbenodigdheden",
    "Telefoon & internet", "Reiskosten", "Autokosten", "Opleiding & vakliteratuur",
    "Representatie", "Verzekeringen", "Bank- en betaalkosten", "Advieskosten",
    "Marketing & website", "Werkruimte", "Overig", INVESTMENT_CAT,
]
ALLOWED_RECEIPTS = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".heic", ".gif"}

DEFAULT_SETTINGS = {
    "bedrijfsnaam": "", "naam": "", "adres": "", "postcode": "", "plaats": "",
    "land": "Nederland", "email": "", "telefoon": "", "website": "",
    "kvk": "", "btw_id": "", "iban": "", "bic": "",
    "betaaltermijn": "30", "factuur_prefix": "",
    "factuur_voettekst": "",
    "mail_onderwerp": "Factuur {nummer} van {bedrijfsnaam}",
    "mail_tekst": ("Beste {klant},\n\nIn de bijlage vind je factuur {nummer} "
                   "van {bedrag}, te voldoen vóór {vervaldatum}.\n\n"
                   "Met vriendelijke groet,\n{naam}\n{bedrijfsnaam}"),
    "logo": "",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, contact TEXT, email TEXT,
    address TEXT, postcode TEXT, city TEXT, country TEXT DEFAULT 'Nederland',
    vat_id TEXT, kvk TEXT
);
CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY, number TEXT UNIQUE,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    date TEXT NOT NULL, due_date TEXT, period TEXT,
    status TEXT NOT NULL DEFAULT 'concept',      -- concept | open | betaald
    vat_mode TEXT NOT NULL DEFAULT 'normaal',
    notes TEXT, paid_date TEXT, credit_of INTEGER REFERENCES invoices(id),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS invoice_lines (
    id INTEGER PRIMARY KEY,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    position INTEGER, description TEXT NOT NULL, quantity REAL NOT NULL,
    unit_price_cents INTEGER NOT NULL, vat_rate INTEGER NOT NULL DEFAULT 21
);
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY, date TEXT NOT NULL, supplier TEXT, description TEXT,
    category TEXT, vat_type TEXT NOT NULL DEFAULT 'nl', vat_rate INTEGER DEFAULT 21,
    total_cents INTEGER NOT NULL, amount_excl_cents INTEGER NOT NULL,
    vat_cents INTEGER NOT NULL DEFAULT 0, receipt_path TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_inv_date ON invoices(date);
CREATE INDEX IF NOT EXISTS ix_exp_date ON expenses(date);
"""


# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------
def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
    for k, v in DEFAULT_SETTINGS.items():
        con.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))
    con.commit()
    con.close()
    key_file = DATA_DIR / ".secret"
    if not key_file.exists():
        key_file.write_text(secrets.token_hex(32))
    app.config["SECRET_KEY"] = key_file.read_text().strip()


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    con = g.pop("db", None)
    if con is not None:
        con.close()


def settings():
    if "settings" not in g:
        g.settings = {r["key"]: r["value"] or "" for r in db().execute("SELECT * FROM settings")}
    return g.settings


@app.context_processor
def inject():
    return {"s": settings(), "VAT_MODES": VAT_MODES, "EXPENSE_VAT_TYPES": EXPENSE_VAT_TYPES,
            "today": dt.date.today().isoformat()}


@app.before_request
def check_password():
    if not PASSWORD:
        return None
    auth = request.authorization
    if auth and secrets.compare_digest(auth.password or "", PASSWORD):
        return None
    return Response("Inloggen vereist", 401, {"WWW-Authenticate": 'Basic realm="Boekhouding"'})


# --------------------------------------------------------------------------
# Geld en datums
# --------------------------------------------------------------------------
def rhu(d) -> int:
    """Rond af op hele centen (half up)."""
    return int(Decimal(d).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def parse_money(value, default=None):
    """'1.234,56' / '1234.56' / '€ 12' -> centen (int)."""
    if value is None:
        return default
    s = str(value).strip().replace("€", "").replace(" ", "").replace(" ", "")
    if not s:
        return default
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return rhu(Decimal(s) * 100)
    except InvalidOperation:
        raise ValueError(f"Ongeldig bedrag: {value}")


def parse_qty(value) -> Decimal:
    s = str(value or "").strip().replace(" ", "")
    if not s:
        return Decimal(1)
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        raise ValueError(f"Ongeldig aantal: {value}")


@app.template_filter("eur")
def eur(cents):
    if cents is None:
        return ""
    cents = int(cents)
    euros, ct = divmod(abs(cents), 100)
    return "€ " + ("-" if cents < 0 else "") + f"{euros:,}".replace(",", ".") + f",{ct:02d}"


@app.template_filter("geld_invoer")
def money_input(cents):
    if cents is None or cents == "":
        return ""
    cents = int(cents)
    euros, ct = divmod(abs(cents), 100)
    return ("-" if cents < 0 else "") + f"{euros},{ct:02d}"


@app.template_filter("aantal")
def fmt_qty(q):
    d = Decimal(str(q)).normalize()
    s = format(d, "f")
    return s.replace(".", ",")


@app.template_filter("datum")
def fmt_date(iso):
    if not iso:
        return ""
    try:
        return dt.date.fromisoformat(iso[:10]).strftime("%d-%m-%Y")
    except ValueError:
        return iso


def parse_date(value, default=None):
    try:
        return dt.date.fromisoformat(value).isoformat()
    except (TypeError, ValueError):
        return default


def quarter_range(year, q):
    start = dt.date(year, 3 * (q - 1) + 1, 1)
    end = dt.date(year + 1, 1, 1) if q == 4 else dt.date(year, 3 * q + 1, 1)
    return start.isoformat(), end.isoformat()


def current_quarter():
    t = dt.date.today()
    return t.year, (t.month - 1) // 3 + 1


def available_years():
    rows = db().execute(
        "SELECT substr(date,1,4) y FROM invoices UNION SELECT substr(date,1,4) FROM expenses"
    ).fetchall()
    years = {int(r["y"]) for r in rows if r["y"]}
    years.add(dt.date.today().year)
    return sorted(years, reverse=True)


# --------------------------------------------------------------------------
# Facturen – berekeningen
# --------------------------------------------------------------------------
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


# --------------------------------------------------------------------------
# Btw-aangifte
# --------------------------------------------------------------------------
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


# --------------------------------------------------------------------------
# Overzicht
# --------------------------------------------------------------------------
@app.route("/")
def dashboard():
    year, q = current_quarter()
    ys, ye = f"{year}-01-01", f"{year + 1}-01-01"
    inv = invoice_summaries("i.status != 'concept' AND i.date >= ? AND i.date < ?", (ys, ye))
    omzet = sum(i["subtotal"] for i in inv)
    kosten = db().execute(
        "SELECT COALESCE(SUM(amount_excl_cents),0) s FROM expenses WHERE date>=? AND date<? AND category != ?",
        (ys, ye, INVESTMENT_CAT)).fetchone()["s"]
    qs, qe = quarter_range(year, q)
    btw = compute_btw(qs, qe)
    open_inv = invoice_summaries("i.status = 'open'")
    concepts = invoice_summaries("i.status = 'concept'")
    recent = db().execute("SELECT * FROM expenses ORDER BY date DESC, id DESC LIMIT 8").fetchall()
    missing = [k for k in ("bedrijfsnaam", "kvk", "btw_id", "iban") if not settings().get(k)]
    return render_template("dashboard.html", year=year, q=q, omzet=omzet, kosten=kosten,
                           btw=btw, open_inv=open_inv, concepts=concepts, recent=recent,
                           missing=missing)


# --------------------------------------------------------------------------
# Klanten
# --------------------------------------------------------------------------
CUSTOMER_FIELDS = ["name", "contact", "email", "address", "postcode", "city", "country", "vat_id", "kvk"]


@app.route("/klanten")
def klanten():
    rows = db().execute(
        """SELECT c.*, (SELECT COUNT(*) FROM invoices i WHERE i.customer_id=c.id) n
           FROM customers c ORDER BY c.name COLLATE NOCASE""").fetchall()
    return render_template("klanten.html", customers=rows)


@app.route("/klanten/nieuw", methods=["GET", "POST"])
@app.route("/klanten/<int:cid>", methods=["GET", "POST"])
def klant_bewerken(cid=None):
    cust = None
    if cid:
        cust = db().execute("SELECT * FROM customers WHERE id=?", (cid,)).fetchone() or abort(404)
    if request.method == "POST":
        vals = {f: request.form.get(f, "").strip() for f in CUSTOMER_FIELDS}
        if not vals["name"]:
            flash("Naam is verplicht.", "error")
            return render_template("klant_form.html", c=vals, cid=cid)
        if cid:
            db().execute(f"UPDATE customers SET {', '.join(f + '=?' for f in CUSTOMER_FIELDS)} WHERE id=?",
                         [vals[f] for f in CUSTOMER_FIELDS] + [cid])
        else:
            cur = db().execute(f"INSERT INTO customers ({', '.join(CUSTOMER_FIELDS)}) VALUES "
                               f"({', '.join('?' * len(CUSTOMER_FIELDS))})",
                               [vals[f] for f in CUSTOMER_FIELDS])
            cid = cur.lastrowid
        db().commit()
        flash("Klant opgeslagen.", "ok")
        nxt = request.args.get("next")
        if nxt == "factuur":
            return redirect(url_for("factuur_nieuw", klant=cid))
        return redirect(url_for("klanten"))
    return render_template("klant_form.html", c=cust or {"country": "Nederland"}, cid=cid)


@app.post("/klanten/<int:cid>/verwijderen")
def klant_verwijderen(cid):
    n = db().execute("SELECT COUNT(*) n FROM invoices WHERE customer_id=?", (cid,)).fetchone()["n"]
    if n:
        flash("Deze klant heeft facturen en kan niet worden verwijderd.", "error")
    else:
        db().execute("DELETE FROM customers WHERE id=?", (cid,))
        db().commit()
        flash("Klant verwijderd.", "ok")
    return redirect(url_for("klanten"))


# --------------------------------------------------------------------------
# Facturen
# --------------------------------------------------------------------------
@app.route("/facturen")
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
        db().execute("UPDATE invoices SET customer_id=?, date=?, due_date=?, period=?, vat_mode=?, notes=? "
                     "WHERE id=?", vals + (inv_id,))
        db().execute("DELETE FROM invoice_lines WHERE invoice_id=?", (inv_id,))
    else:
        inv_id = db().execute("INSERT INTO invoices (customer_id, date, due_date, period, vat_mode, notes) "
                              "VALUES (?,?,?,?,?,?)", vals).lastrowid
    db().executemany("INSERT INTO invoice_lines (invoice_id, position, description, quantity, "
                     "unit_price_cents, vat_rate) VALUES (?,?,?,?,?,?)",
                     [(inv_id,) + ln for ln in lines])
    db().commit()
    return inv_id


def _form_lines():
    f = request.form
    return [{"description": d, "quantity": q, "unit_price": p, "vat_rate": r}
            for d, q, p, r in zip(f.getlist("description"), f.getlist("quantity"),
                                  f.getlist("unit_price"), f.getlist("vat_rate"))]


@app.route("/facturen/nieuw", methods=["GET", "POST"])
def factuur_nieuw():
    customers = db().execute("SELECT * FROM customers ORDER BY name COLLATE NOCASE").fetchall()
    if request.method == "POST":
        try:
            inv_id = _save_invoice_form()
            flash("Concept opgeslagen. Controleer en maak de factuur definitief.", "ok")
            return redirect(url_for("factuur", inv_id=inv_id))
        except ValueError as e:
            flash(str(e), "error")
            return render_template("factuur_form.html", inv=request.form, lines=_form_lines(),
                                   customers=customers, from_form=True)
    inv = {"customer_id": request.args.get("klant", type=int), "vat_mode": "normaal",
           "date": dt.date.today().isoformat()}
    return render_template("factuur_form.html", inv=inv, lines=[], customers=customers)


@app.route("/facturen/<int:inv_id>/bewerken", methods=["GET", "POST"])
def factuur_bewerken(inv_id):
    inv, cust, lines = load_invoice(inv_id)
    if inv["status"] != "concept":
        flash("Een definitieve factuur kun je niet meer wijzigen. Maak een creditfactuur.", "error")
        return redirect(url_for("factuur", inv_id=inv_id))
    customers = db().execute("SELECT * FROM customers ORDER BY name COLLATE NOCASE").fetchall()
    if request.method == "POST":
        try:
            _save_invoice_form(inv_id)
            flash("Concept bijgewerkt.", "ok")
            return redirect(url_for("factuur", inv_id=inv_id))
        except ValueError as e:
            flash(str(e), "error")
            return render_template("factuur_form.html", inv=request.form, lines=_form_lines(),
                                   customers=customers, inv_id=inv_id, from_form=True)
    form_lines = [{"description": l["description"], "quantity": fmt_qty(l["quantity"]),
                   "unit_price": money_input(l["unit_price_cents"]), "vat_rate": str(l["vat_rate"])}
                  for l in lines]
    return render_template("factuur_form.html", inv=inv, lines=form_lines, customers=customers,
                           inv_id=inv_id)


@app.route("/facturen/<int:inv_id>")
def factuur(inv_id):
    inv, cust, lines = load_invoice(inv_id)
    totals = invoice_totals(lines, inv["vat_mode"])
    credit_of = None
    if inv["credit_of"]:
        credit_of = db().execute("SELECT id, number FROM invoices WHERE id=?", (inv["credit_of"],)).fetchone()
    credits = db().execute("SELECT id, number, status FROM invoices WHERE credit_of=?", (inv_id,)).fetchall()
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


@app.post("/facturen/<int:inv_id>/definitief")
def factuur_definitief(inv_id):
    inv, cust, lines = load_invoice(inv_id)
    if inv["status"] != "concept":
        return redirect(url_for("factuur", inv_id=inv_id))
    s = settings()
    missing = [n for k, n in [("bedrijfsnaam", "bedrijfsnaam"), ("kvk", "KvK-nummer"),
                              ("btw_id", "btw-id"), ("iban", "IBAN"), ("adres", "adres")] if not s.get(k)]
    if missing:
        flash("Vul eerst je bedrijfsgegevens aan bij Instellingen: " + ", ".join(missing) + ".", "error")
        return redirect(url_for("factuur", inv_id=inv_id))
    if inv["vat_mode"] == "eu_b2b" and not cust["vat_id"]:
        flash("Bij btw verleggen naar een EU-klant is het btw-id van de klant verplicht.", "error")
        return redirect(url_for("factuur", inv_id=inv_id))
    year = inv["date"][:4]
    number = next_invoice_number(year)
    db().execute("UPDATE invoices SET number=?, status='open' WHERE id=?", (number, inv_id))
    if inv["credit_of"]:
        orig, _, orig_lines = load_invoice(inv["credit_of"])
        own = invoice_totals(lines, inv["vat_mode"])["total"]
        if orig["status"] == "open" and invoice_totals(orig_lines, orig["vat_mode"])["total"] + own == 0:
            today = dt.date.today().isoformat()
            db().execute("UPDATE invoices SET status='betaald', paid_date=? WHERE id IN (?, ?)",
                         (today, inv_id, orig["id"]))
            flash("Factuur en creditnota heffen elkaar op en zijn als afgehandeld gemarkeerd.", "ok")
    db().commit()
    flash(f"Factuur {number} is definitief.", "ok")
    return redirect(url_for("factuur", inv_id=inv_id))


@app.post("/facturen/<int:inv_id>/betaald")
def factuur_betaald(inv_id):
    paid = parse_date(request.form.get("paid_date")) or dt.date.today().isoformat()
    db().execute("UPDATE invoices SET status='betaald', paid_date=? WHERE id=? AND status='open'",
                 (paid, inv_id))
    db().commit()
    flash("Gemarkeerd als betaald.", "ok")
    return redirect(request.form.get("back") or url_for("factuur", inv_id=inv_id))


@app.post("/facturen/<int:inv_id>/heropenen")
def factuur_heropenen(inv_id):
    db().execute("UPDATE invoices SET status='open', paid_date=NULL WHERE id=? AND status='betaald'",
                 (inv_id,))
    db().commit()
    return redirect(url_for("factuur", inv_id=inv_id))


@app.post("/facturen/<int:inv_id>/verwijderen")
def factuur_verwijderen(inv_id):
    inv, _, _ = load_invoice(inv_id)
    if inv["status"] != "concept":
        flash("Alleen concepten kunnen worden verwijderd.", "error")
        return redirect(url_for("factuur", inv_id=inv_id))
    db().execute("DELETE FROM invoices WHERE id=?", (inv_id,))
    db().commit()
    flash("Concept verwijderd.", "ok")
    return redirect(url_for("facturen"))


@app.post("/facturen/<int:inv_id>/crediteren")
def factuur_crediteren(inv_id):
    inv, cust, lines = load_invoice(inv_id)
    if inv["status"] == "concept":
        return redirect(url_for("factuur", inv_id=inv_id))
    today = dt.date.today().isoformat()
    new_id = db().execute(
        "INSERT INTO invoices (customer_id, date, due_date, period, vat_mode, notes, credit_of) "
        "VALUES (?,?,?,?,?,?,?)",
        (inv["customer_id"], today, today, inv["period"], inv["vat_mode"],
         f"Creditering van factuur {inv['number']}.", inv_id)).lastrowid
    db().executemany(
        "INSERT INTO invoice_lines (invoice_id, position, description, quantity, unit_price_cents, vat_rate) "
        "VALUES (?,?,?,?,?,?)",
        [(new_id, l["position"], l["description"], -l["quantity"], l["unit_price_cents"], l["vat_rate"])
         for l in lines])
    db().commit()
    flash("Creditfactuur als concept aangemaakt. Pas eventueel aan en maak definitief.", "ok")
    return redirect(url_for("factuur", inv_id=new_id))


@app.route("/facturen/<int:inv_id>/pdf")
def factuur_pdf(inv_id):
    from pdf import build_invoice_pdf
    inv, cust, lines = load_invoice(inv_id)
    totals = invoice_totals(lines, inv["vat_mode"])
    credit_of = None
    if inv["credit_of"]:
        r = db().execute("SELECT number FROM invoices WHERE id=?", (inv["credit_of"],)).fetchone()
        credit_of = r["number"] if r else None
    s = settings()
    logo = DATA_DIR / s["logo"] if s.get("logo") else None
    data = build_invoice_pdf(inv, cust, lines, totals, s, logo if logo and logo.exists() else None,
                             helpers={"eur": eur, "datum": fmt_date, "aantal": fmt_qty,
                                      "line_amount": line_amount},
                             vat_text=VAT_MODE_TEXT.get(inv["vat_mode"]), credit_of=credit_of)
    name = f"Factuur {inv['number']}.pdf" if inv["number"] else f"Concept factuur {inv_id}.pdf"
    if inv["credit_of"] and inv["number"]:
        name = f"Creditfactuur {inv['number']}.pdf"
    return send_file(io.BytesIO(data), mimetype="application/pdf", download_name=name,
                     as_attachment=request.args.get("download") == "1")


# --------------------------------------------------------------------------
# Kosten
# --------------------------------------------------------------------------
def categories():
    used = [r["category"] for r in db().execute(
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


@app.route("/kosten")
def kosten():
    year = request.args.get("jaar", type=int) or dt.date.today().year
    q = request.args.get("kwartaal", type=int)
    cat = request.args.get("categorie", "")
    start, end = quarter_range(year, q) if q in (1, 2, 3, 4) else (f"{year}-01-01", f"{year + 1}-01-01")
    sql, params = "SELECT * FROM expenses WHERE date >= ? AND date < ?", [start, end]
    if cat:
        sql += " AND category = ?"
        params.append(cat)
    rows = db().execute(sql + " ORDER BY date DESC, id DESC", params).fetchall()
    sums = {k: sum(r[k] for r in rows) for k in ("amount_excl_cents", "vat_cents", "total_cents")}
    return render_template("kosten.html", expenses=rows, sums=sums, year=year, q=q, cat=cat,
                           years=available_years(), categories=categories())


def _store_receipt(exp_id, date, file):
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_RECEIPTS:
        raise ValueError(f"Bestandstype {ext or '?'} niet toegestaan (pdf, jpg, png, webp, heic).")
    folder = UPLOAD_DIR / date[:4]
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{exp_id:05d}_{secure_filename(file.filename) or 'bon' + ext}"
    file.save(folder / name)
    return f"{date[:4]}/{name}"


def _delete_receipt(rel):
    if rel:
        p = (UPLOAD_DIR / rel).resolve()
        if p.is_file() and UPLOAD_DIR in p.parents:
            p.unlink()


@app.route("/kosten/nieuw", methods=["GET", "POST"])
@app.route("/kosten/<int:eid>", methods=["GET", "POST"])
def kosten_bewerken(eid=None):
    exp = None
    if eid:
        exp = db().execute("SELECT * FROM expenses WHERE id=?", (eid,)).fetchone() or abort(404)
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
                db().execute("UPDATE expenses SET date=?, supplier=?, description=?, category=?, vat_type=?, "
                             "vat_rate=?, total_cents=?, amount_excl_cents=?, vat_cents=? WHERE id=?",
                             vals + (eid,))
            else:
                eid = db().execute("INSERT INTO expenses (date, supplier, description, category, vat_type, "
                                   "vat_rate, total_cents, amount_excl_cents, vat_cents) "
                                   "VALUES (?,?,?,?,?,?,?,?,?)", vals).lastrowid
            file = request.files.get("receipt")
            if file and file.filename:
                old = exp["receipt_path"] if exp else None
                rel = _store_receipt(eid, date, file)
                db().execute("UPDATE expenses SET receipt_path=? WHERE id=?", (rel, eid))
                if old and old != rel:
                    _delete_receipt(old)
            elif f.get("remove_receipt") and exp and exp["receipt_path"]:
                _delete_receipt(exp["receipt_path"])
                db().execute("UPDATE expenses SET receipt_path=NULL WHERE id=?", (eid,))
            db().commit()
        except ValueError as e:
            db().rollback()
            flash(str(e), "error")
            vals = {k: f.get(k, "") for k in ("date", "supplier", "description", "category", "vat_type",
                                              "vat_rate", "total", "vat_override")}
            vals["receipt_path"] = exp["receipt_path"] if exp else None
            return render_template("kosten_form.html", e=vals, eid=exp["id"] if exp else None,
                                   categories=categories())
        flash("Kosten opgeslagen.", "ok")
        if f.get("again"):
            return redirect(url_for("kosten_bewerken"))
        return redirect(url_for("kosten", jaar=date[:4]))
    if exp:
        _, auto_vat = calc_expense(exp["total_cents"], exp["vat_type"], exp["vat_rate"], None)
        vals = {"date": exp["date"], "supplier": exp["supplier"] or "", "description": exp["description"] or "",
                "category": exp["category"] or "", "vat_type": exp["vat_type"], "vat_rate": str(exp["vat_rate"]),
                "total": money_input(exp["total_cents"]),
                "vat_override": money_input(exp["vat_cents"]) if exp["vat_cents"] != auto_vat else "",
                "receipt_path": exp["receipt_path"], "amount_excl_cents": exp["amount_excl_cents"],
                "vat_cents": exp["vat_cents"]}
    else:
        vals = {"date": dt.date.today().isoformat(), "vat_type": "nl", "vat_rate": "21"}
    return render_template("kosten_form.html", e=vals, eid=eid, categories=categories())


@app.post("/kosten/<int:eid>/verwijderen")
def kosten_verwijderen(eid):
    exp = db().execute("SELECT * FROM expenses WHERE id=?", (eid,)).fetchone() or abort(404)
    _delete_receipt(exp["receipt_path"])
    db().execute("DELETE FROM expenses WHERE id=?", (eid,))
    db().commit()
    flash("Kosten verwijderd.", "ok")
    return redirect(url_for("kosten", jaar=exp["date"][:4]))


@app.route("/kosten/<int:eid>/bon")
def kosten_bon(eid):
    exp = db().execute("SELECT receipt_path FROM expenses WHERE id=?", (eid,)).fetchone()
    if not exp or not exp["receipt_path"]:
        abort(404)
    p = (UPLOAD_DIR / exp["receipt_path"]).resolve()
    if UPLOAD_DIR not in p.parents or not p.is_file():
        abort(404)
    return send_file(p)


# --------------------------------------------------------------------------
# Btw en jaaroverzicht
# --------------------------------------------------------------------------
@app.route("/btw")
def btw():
    cy, cq = current_quarter()
    year = request.args.get("jaar", type=int) or cy
    q = request.args.get("kwartaal", type=int) or cq
    start, end = quarter_range(year, q)
    data = compute_btw(start, end)
    # Aangifte en betaling uiterlijk de laatste dag van de maand na het kwartaal
    first_next = dt.date.fromisoformat(end)
    last_day = (first_next.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
    concepts = db().execute("SELECT COUNT(*) n FROM invoices WHERE status='concept' AND date>=? AND date<?",
                            (start, end)).fetchone()["n"]
    return render_template("btw.html", d=data, year=year, q=q, years=available_years(),
                           deadline=last_day.isoformat(), concepts=concepts)


@app.route("/jaar")
def jaar():
    year = request.args.get("jaar", type=int) or dt.date.today().year
    ys, ye = f"{year}-01-01", f"{year + 1}-01-01"
    inv = invoice_summaries("i.status != 'concept' AND i.date >= ? AND i.date < ?", (ys, ye))
    omzet = sum(i["subtotal"] for i in inv)
    btw_gefactureerd = sum(i["vat"] for i in inv)
    cats = db().execute(
        "SELECT category, COUNT(*) n, SUM(amount_excl_cents) excl, SUM(vat_cents) vat FROM expenses "
        "WHERE date>=? AND date<? AND category != ? GROUP BY category ORDER BY excl DESC",
        (ys, ye, INVESTMENT_CAT)).fetchall()
    kosten_tot = sum(c["excl"] for c in cats)
    investments = db().execute("SELECT * FROM expenses WHERE date>=? AND date<? AND category=? ORDER BY date",
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


# --------------------------------------------------------------------------
# Instellingen, export en back-up
# --------------------------------------------------------------------------
@app.route("/instellingen", methods=["GET", "POST"])
def instellingen():
    if request.method == "POST":
        for k in DEFAULT_SETTINGS:
            if k == "logo":
                continue
            if k in request.form:
                db().execute("UPDATE settings SET value=? WHERE key=?", (request.form[k].strip(), k))
        logo = request.files.get("logo")
        if logo and logo.filename:
            ext = Path(logo.filename).suffix.lower()
            if ext not in (".png", ".jpg", ".jpeg"):
                flash("Logo moet een PNG of JPG zijn.", "error")
            else:
                for old in DATA_DIR.glob("logo.*"):
                    old.unlink()
                logo.save(DATA_DIR / f"logo{ext}")
                db().execute("UPDATE settings SET value=? WHERE key='logo'", (f"logo{ext}",))
        if request.form.get("remove_logo"):
            for old in DATA_DIR.glob("logo.*"):
                old.unlink()
            db().execute("UPDATE settings SET value='' WHERE key='logo'")
        db().commit()
        flash("Instellingen opgeslagen.", "ok")
        return redirect(url_for("instellingen"))
    return render_template("instellingen.html", data_dir=str(DATA_DIR), years=available_years())


@app.route("/logo")
def logo():
    s = settings()
    p = DATA_DIR / s["logo"] if s.get("logo") else None
    if not p or not p.is_file():
        abort(404)
    return send_file(p)


@app.route("/export/<kind>.csv")
def export(kind):
    year = request.args.get("jaar", type=int) or dt.date.today().year
    ys, ye = f"{year}-01-01", f"{year + 1}-01-01"
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")

    def c2s(c):
        return money_input(c)

    if kind == "facturen":
        w.writerow(["Factuurnummer", "Datum", "Vervaldatum", "Klant", "Btw-id klant", "Status",
                    "Btw-situatie", "Excl. btw", "Btw", "Totaal", "Betaald op", "Creditering van"])
        for i in sorted(invoice_summaries("i.status != 'concept' AND i.date>=? AND i.date<?", (ys, ye)),
                        key=lambda x: x["number"]):
            orig = ""
            if i["credit_of"]:
                r = db().execute("SELECT number FROM invoices WHERE id=?", (i["credit_of"],)).fetchone()
                orig = r["number"] if r else ""
            w.writerow([i["number"], i["date"], i["due_date"], i["cname"], i["cvat"] or "", i["status"],
                        i["vat_mode"], c2s(i["subtotal"]), c2s(i["vat"]), c2s(i["total"]),
                        i["paid_date"] or "", orig])
    elif kind == "kosten":
        w.writerow(["Datum", "Leverancier", "Omschrijving", "Categorie", "Btw-soort", "Tarief",
                    "Excl. btw", "Btw", "Totaal", "Bon"])
        for e in db().execute("SELECT * FROM expenses WHERE date>=? AND date<? ORDER BY date, id", (ys, ye)):
            w.writerow([e["date"], e["supplier"], e["description"], e["category"], e["vat_type"],
                        e["vat_rate"], c2s(e["amount_excl_cents"]), c2s(e["vat_cents"]),
                        c2s(e["total_cents"]), e["receipt_path"] or ""])
    else:
        abort(404)
    data = "﻿" + buf.getvalue()  # BOM zodat Excel de tekens goed leest
    return Response(data, mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{kind}_{year}.csv"'})


@app.route("/backup")
def backup():
    with tempfile.TemporaryDirectory() as tmp:
        snap = Path(tmp) / "boekhouding.db"
        src = sqlite3.connect(DB_PATH)
        dst = sqlite3.connect(snap)
        src.backup(dst)
        dst.close()
        src.close()
        mem = io.BytesIO()
        with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(snap, "boekhouding.db")
            for p in DATA_DIR.rglob("*"):
                if p.is_file() and p.name not in ("boekhouding.db", ".secret") and not p.name.endswith(
                        ("-wal", "-shm", "-journal")):
                    z.write(p, p.relative_to(DATA_DIR).as_posix())
        mem.seek(0)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    return send_file(mem, mimetype="application/zip", as_attachment=True,
                     download_name=f"boekhouding-backup-{stamp}.zip")


init_db()

if __name__ == "__main__":
    host = os.environ.get("BOEKHOUDING_HOST", "127.0.0.1")
    port = int(os.environ.get("BOEKHOUDING_PORT", "5000"))
    print(f"Boekhouding draait op http://{host}:{port}  (data: {DATA_DIR})")
    app.run(host=host, port=port, debug=False)
