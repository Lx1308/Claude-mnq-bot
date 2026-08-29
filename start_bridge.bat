@echo off
cd /d "%~dp0"
title TRADAYRI Bridge (NT8 Receiver)
echo Starte TRADAYRI Bridge im Dauerbetrieb...
.venv\Scripts\python.exe -u -m ntbridge
pause
