@echo off
cd /d "%~dp0"
title TradeX Bridge (NT8 Receiver)
echo Starte TradeX Bridge im Dauerbetrieb...
.venv\Scripts\python.exe -u -m ntbridge
pause
