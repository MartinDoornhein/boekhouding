"""`python -m boekhouding`: start de ingebouwde server (host/poort via omgevingsvariabelen)."""
import os

from . import create_app

app = create_app()
host = os.environ.get("BOEKHOUDING_HOST", "127.0.0.1")
port = int(os.environ.get("BOEKHOUDING_PORT", "5000"))
print(f"Boekhouding draait op http://{host}:{port}  (data: {app.config['DATA_DIR']})")
app.run(host=host, port=port, debug=False)
