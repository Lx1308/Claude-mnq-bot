@echo off
echo ===================================
echo   TRADAYRI Desktop App - Starte...
echo ===================================
echo.

cd /d "%~dp0"
set PYTHONPATH=%cd%

echo Projektverzeichnis: %cd%
echo.

.venv\Scripts\python.exe -u desktop_app.py

echo.
echo Beendet.
pause
