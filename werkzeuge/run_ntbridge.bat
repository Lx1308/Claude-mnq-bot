@echo off
rem Empfaenger fuer NT8-Kerzen, als eigenstaendiger Windows-Prozess ueber
rem die Aufgabenplanung gestartet - unabhaengig von jeder Claude-Sitzung.
cd /d "C:\Users\lm130\Desktop\Claude chart bot"
"C:\Users\lm130\Desktop\Claude chart bot\.venv\Scripts\python.exe" -m ntbridge
