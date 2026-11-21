import io
import sqlite3
import zipfile

from boekhouding import create_app

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4"
       b"\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf\xc0\xf0\x1f\x00\x05\x00\x01\xff\x89\x99=\x1d\x00\x00\x00\x00IEND\xaeB`\x82")


def add_expense(client, receipt=b"%PDF-1", name="bon.pdf", eid=None):
    return client.post(f"/kosten/{eid}" if eid else "/kosten/nieuw", content_type="multipart/form-data", data={
        "date": "2026-11-02", "total": "121,00", "vat_type": "nl", "vat_rate": "21",
        "receipt": (io.BytesIO(receipt), name)})


def count_files(app):
    con = sqlite3.connect(app.config["DATABASE"])
    n = con.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    con.close()
    return n


def test_receipt_stored_in_db_and_replaced(app, client):
    add_expense(client)
    assert client.get("/kosten/1/bon").data == b"%PDF-1"
    assert not (app.config["DATA_DIR"] / "bonnen").exists()
    add_expense(client, b"%PDF-2", eid=1)  # vervangen: oude BLOB wordt opgeruimd
    assert client.get("/kosten/1/bon").data == b"%PDF-2"
    assert count_files(app) == 1
    client.post("/kosten/1/verwijderen")
    assert count_files(app) == 0


def test_receipt_wrong_type_rolls_back(app, client):
    r = add_expense(client, b"MZ", "virus.exe")
    assert r.status_code == 200 and "niet toegestaan" in r.get_data(as_text=True)
    assert count_files(app) == 0


def test_logo_in_db_and_pdf(app, client, company):
    client.post("/instellingen", content_type="multipart/form-data", data={"logo": (io.BytesIO(PNG), "logo.png")})
    assert client.get("/logo").data == PNG
    client.post("/klanten/nieuw", data={"name": "Klant"})
    client.post("/facturen/nieuw", data={"customer_id": "1", "description": ["x"], "unit_price": ["10"],
                                         "quantity": ["1"], "vat_rate": ["21"]})
    assert client.get("/facturen/1/pdf").status_code == 200
    client.post("/instellingen", data={"remove_logo": "1"})
    assert client.get("/logo").status_code == 404
    assert count_files(app) == 0


def test_backup_zip_contains_db_and_receipts(client):
    add_expense(client)
    z = zipfile.ZipFile(io.BytesIO(client.get("/backup").data))
    assert "boekhouding.db" in z.namelist()
    assert z.read("bonnen/2026/00001_bon.pdf") == b"%PDF-1"


def test_archive_command(app, tmp_path):
    out = tmp_path / "archief.zip"
    result = app.test_cli_runner().invoke(args=["archive", "-o", str(out)])
    assert result.exit_code == 0 and zipfile.is_zipfile(out)


def test_migrates_old_files_on_disk(tmp_path):
    """Database van vóór deze versie: receipt_path + bestanden in data/bonnen, logo als bestand."""
    data = tmp_path / "data"
    (data / "bonnen" / "2025").mkdir(parents=True)
    (data / "bonnen" / "2025" / "00001_bon.pdf").write_bytes(b"%PDF-oud")
    (data / "logo.png").write_bytes(PNG)
    con = sqlite3.connect(data / "boekhouding.db")
    con.executescript("""
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO settings VALUES ('logo', 'logo.png');
        CREATE TABLE expenses (id INTEGER PRIMARY KEY, date TEXT NOT NULL, supplier TEXT, description TEXT,
            category TEXT, vat_type TEXT NOT NULL DEFAULT 'nl', vat_rate INTEGER DEFAULT 21,
            total_cents INTEGER NOT NULL, amount_excl_cents INTEGER NOT NULL,
            vat_cents INTEGER NOT NULL DEFAULT 0, receipt_path TEXT, created_at TEXT);
        INSERT INTO expenses (id, date, total_cents, amount_excl_cents, receipt_path)
            VALUES (1, '2025-03-01', 121, 100, '2025/00001_bon.pdf');
    """)
    con.close()

    client = create_app({"DATA_DIR": data}).test_client()
    assert client.get("/kosten/1/bon").data == b"%PDF-oud"
    assert client.get("/logo").data == PNG
    create_app({"DATA_DIR": data})  # tweede start: niets dubbel
    con = sqlite3.connect(data / "boekhouding.db")
    assert con.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 2
