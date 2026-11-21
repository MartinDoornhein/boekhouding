import pytest

from boekhouding import create_app


@pytest.fixture
def app(tmp_path):
    return create_app({"TESTING": True, "DATA_DIR": tmp_path, "SECRET_KEY": "test"})


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def company(client):
    """Bedrijfsgegevens invullen, zodat facturen definitief gemaakt kunnen worden."""
    client.post("/instellingen", data={"bedrijfsnaam": "Test BV", "kvk": "1", "btw_id": "NL1",
                                       "iban": "NL00TEST0000000000", "adres": "Straat 1"})
