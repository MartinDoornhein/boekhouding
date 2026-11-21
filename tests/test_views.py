import io

import pytest


@pytest.fixture
def invoice(client, company):
    client.post("/klanten/nieuw", data={"name": "Klant A", "vat_id": "DE1"})
    client.post("/facturen/nieuw", data={
        "customer_id": "1", "date": "2026-11-01", "vat_mode": "normaal",
        "description": ["Werk"], "quantity": ["2"], "unit_price": ["1.000,50"], "vat_rate": ["21"]})
    client.post("/facturen/1/definitief")


@pytest.fixture
def expense(client):
    client.post("/kosten/nieuw", content_type="multipart/form-data", data={
        "date": "2026-11-02", "total": "€ 121,00", "vat_type": "nl", "vat_rate": "21",
        "receipt": (io.BytesIO(b"%PDF-1"), "bon.pdf")})


@pytest.mark.parametrize("path", [
    "/", "/klanten", "/klanten/nieuw", "/facturen", "/facturen/nieuw", "/kosten", "/kosten/nieuw",
    "/btw", "/jaar", "/instellingen", "/export/facturen.csv", "/export/kosten.csv", "/backup",
])
def test_pages_empty(client, path):
    assert client.get(path).status_code == 200


def test_invoice_flow(client, invoice):
    html = client.get("/facturen/1").get_data(as_text=True)
    assert "2026-001" in html
    assert "€ 2.421,21" in html
    assert client.get("/facturen/1/pdf").mimetype == "application/pdf"
    assert client.get("/facturen/1/bewerken").status_code == 302  # definitief: niet meer te wijzigen

    client.post("/facturen/1/crediteren")
    client.post("/facturen/2/definitief")
    csv = client.get("/export/facturen.csv?jaar=2026").get_data(as_text=True)
    assert "2026-002" in csv and "-2421,21" in csv


def test_expense_and_btw(client, invoice, expense):
    assert client.get("/kosten/1/bon").data == b"%PDF-1"
    html = client.get("/btw?jaar=2026&kwartaal=4").get_data(as_text=True)
    assert "420,21" in html  # btw rubriek 1a
    assert "21,00" in html  # voorbelasting
    assert client.get("/jaar?jaar=2026").status_code == 200


def test_active_nav(client, invoice):
    html = client.get("/facturen/1").get_data(as_text=True)
    assert html.count('class="on"') == 1
