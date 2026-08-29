@echo off
cd /d "C:\Users\lm130\Desktop\Claude chart bot"

:: Bridge im Hintergrund (ohne sichtbares Fenster) starten ueber pythonw
start "" /B .venv\Scripts\pythonw.exe -m ntbridge

:: NinjaTrader starten
start "" "C:\Program Files\NinjaTrader 8\bin\NinjaTrader.exe"
