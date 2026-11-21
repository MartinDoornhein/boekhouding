from boekhouding import create_app


def test_config(tmp_path):
    assert not create_app({"DATA_DIR": tmp_path}).testing
    assert create_app({"TESTING": True, "DATA_DIR": tmp_path}).testing


def test_data_dir_is_created(tmp_path):
    app = create_app({"DATA_DIR": tmp_path / "data"})
    assert app.config["DATABASE"].is_file()
    assert app.config["UPLOAD_DIR"].is_dir()
    assert (tmp_path / "data" / ".secret").is_file()


def test_password(tmp_path):
    client = create_app({"DATA_DIR": tmp_path, "PASSWORD": "geheim"}).test_client()
    assert client.get("/").status_code == 401
    assert client.get("/", auth=("x", "fout")).status_code == 401
    assert client.get("/", auth=("x", "geheim")).status_code == 200
