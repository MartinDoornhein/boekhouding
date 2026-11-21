-- Idempotent: wordt bij elke start uitgevoerd en wist nooit bestaande data.
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
