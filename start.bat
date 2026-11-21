@echo off
rem Start de boekhouding (Windows). Eerste keer maakt hij een virtualenv aan.
cd /d "%~dp0"
if not exist .venv (
  py -3 -m venv .venv || python -m venv .venv
  .venv\Scripts\pip install -q -r requirements.txt
)
start "" http://127.0.0.1:5000
.venv\Scripts\python app.py
