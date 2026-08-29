"""
TradeX Desktop App Launcher.

Startet den Execution Server als Unterprozess und oeffnet danach
ein pywebview-Fenster. Beim Schliessen des Fensters wird der Server
sauber beendet.
"""

import os
import sys
import time
import socket
import subprocess


def wait_until_ready(host: str, port: int, server_proc: subprocess.Popen, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if server_proc.poll() is not None:
            print("FEHLER: Der Execution Server Prozess hat sich unerwartet beendet!")
            return False
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.5)
            if probe.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.5)
    return False


def main():
    host = '127.0.0.1'
    port = 8790

    # Sicherstellen, dass wir im Projektverzeichnis arbeiten
    project_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_dir)

    # PYTHONPATH setzen, damit execution/server.py seine Imports findet
    env = os.environ.copy()
    env['PYTHONPATH'] = project_dir

    print(f"Projektverzeichnis: {project_dir}")
    print("Starte Execution Server...")

    server_process = subprocess.Popen(
        [sys.executable, os.path.join("execution", "server.py")],
        env=env,
        cwd=project_dir,
    )

    print(f"Warte auf Server (Port {port})...")
    if not wait_until_ready(host, port, server_process):
        print(f"FEHLER: Server ist nicht innerhalb von 30s auf Port {port} gestartet.")
        print("Pruefe execution/server.py auf Fehler.")
        server_process.kill()
        input("Druecke Enter zum Schliessen...")
        return

    print("Server bereit. Oeffne Fenster...")

    try:
        import webview
    except ImportError:
        print("FEHLER: pywebview nicht installiert.")
        print("Installiere mit: .venv\\Scripts\\python.exe -m pip install pywebview")
        server_process.kill()
        input("Druecke Enter zum Schliessen...")
        return

    window = webview.create_window(
        "TradeX - NinjaTrader Live Bot",
        f"http://{host}:{port}",
        width=1680,
        height=1000,
        min_size=(1100, 700),
        background_color="#0d1117",
    )

    try:
        print("Starte Webview Event Loop (Edge Chromium)...")
        webview.start(gui='edgechromium', debug=True)
    except Exception as e:
        print(f"FEHLER beim Starten von Webview: {e}")
        input("Druecke Enter zum Schliessen...")

    # Fenster geschlossen -> Server beenden
    print("Fenster geschlossen. Beende Server...")
    server_process.terminate()
    try:
        server_process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        server_process.kill()
        server_process.wait()
    print("Server beendet.")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        input("KRITISCHER FEHLER aufgetreten. Druecke Enter zum Schliessen...")
