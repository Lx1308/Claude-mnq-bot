@echo off
REM ---------------------------------------------------------------------------
REM Wrapper fuer die taegliche Datenluecken-Pruefung.
REM
REM Warum ein Wrapper und nicht alles in der schtasks-Befehlszeile:
REM Die Aufgabenplanung startet Programme ohne definiertes Arbeitsverzeichnis.
REM Das Pruefskript sucht seine Datenbank aber relativ ("data/ntbridge.sqlite3").
REM Ohne das "cd /d" unten wuerde die Aufgabe taeglich mit "Datenbank nicht
REM gefunden" fehlschlagen - und zwar lautlos, weil niemand hinschaut.
REM
REM Die Ausgabe wird ANGEHAENGT, nie ueberschrieben: der Verlauf ueber Wochen
REM ist der eigentliche Wert. Wann eine Luecke entstand, laesst sich sonst
REM nachtraeglich nicht mehr feststellen.
REM ---------------------------------------------------------------------------

cd /d "C:\Users\lm130\Desktop\Claude chart bot"

set LOGDATEI=datenluecken_log.txt

echo.>> "%LOGDATEI%"
echo ######################################################################>> "%LOGDATEI%"
echo # Lauf vom %DATE% %TIME%>> "%LOGDATEI%"
echo ######################################################################>> "%LOGDATEI%"

REM stderr mit in die Logdatei, sonst ginge ein Absturz des Skripts verloren.
".venv\Scripts\python.exe" pruefe_datenluecken.py >> "%LOGDATEI%" 2>&1
set ERGEBNIS=%ERRORLEVEL%

REM Exitcodes des Pruefskripts: 0 = keine Luecke, 2 = Luecken gefunden,
REM 1 = Skript konnte nicht pruefen (z.B. Datenbank fehlt). Der Unterschied
REM zwischen 1 und 2 ist wichtig: 1 heisst "keine Aussage moeglich".
echo [Exitcode %ERRORLEVEL% - 0=sauber, 2=Luecken gefunden, 1=Pruefung fehlgeschlagen]>> "%LOGDATEI%"

exit /b %ERGEBNIS%
