"""SQLite-verbinding, schema en instellingen."""
import datetime as dt
import secrets
import sqlite3

from flask import g

from config import DATA_DIR, DB_PATH, DEFAULT_SETTINGS, UPLOAD_DIR

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


def init_db():
    """Maak mappen, tabellen en standaardinstellingen aan. Geeft de secret key terug."""
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
    return key_file.read_text().strip()


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc):
    con = g.pop("db", None)
    if con is not None:
        con.close()


def settings():
    if "settings" not in g:
        g.settings = {r["key"]: r["value"] or "" for r in db().execute("SELECT * FROM settings")}
    return g.settings


def available_years():
    rows = db().execute(
        "SELECT substr(date,1,4) y FROM invoices UNION SELECT substr(date,1,4) FROM expenses"
    ).fetchall()
    years = {int(r["y"]) for r in rows if r["y"]}
    years.add(dt.date.today().year)
    return sorted(years, reverse=True)
