@echo off
rem Start de boekhouding (Windows). Eerste keer maakt hij een virtualenv aan.
cd /d "%~dp0"
if not exist .venv (
  py -3 -m venv .venv || python -m venv .venv
  .venv\Scripts\pip install -q -e .
)
start "" http://127.0.0.1:5050
.venv\Scripts\python -m boekhouding
