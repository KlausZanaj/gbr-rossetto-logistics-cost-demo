"""Launch a local headless server, check HTTP, stop it, verify port release."""
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request


def main():
    root = Path(__file__).resolve().parents[1]
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    output = root / "outputs"
    output.mkdir(exist_ok=True)
    with (output / "http-check.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "app.py", "--server.headless=true", f"--server.port={port}", "--server.address=127.0.0.1", "--browser.gatherUsageStats=false"],
                                   cwd=root, stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        try:
            deadline = time.monotonic() + 30
            while True:
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as response:
                        assert response.status == 200 and b"streamlit" in response.read().lower()
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=2) as response:
                        assert response.status == 200
                    print(f"Streamlit headless: pagina e health HTTP 200 su porta {port}.")
                    break
                except (OSError, AssertionError):
                    if process.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError("Avvio HTTP fallito: consultare outputs/http-check.log")
                    time.sleep(0.2)
        finally:
            if sys.platform == "win32" and process.poll() is None:
                # The venv launcher can spawn a child interpreter on Windows.
                # Stop only this known server process tree, before its parent.
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], check=True, capture_output=True)
            elif process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    with socket.socket() as sock:
        assert sock.connect_ex(("127.0.0.1", port)) != 0, "Server ancora in ascolto."
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", port))
    print("Server arrestato e porta rilasciata. HTTP non prova l'intero flusso utente.")


if __name__ == "__main__":
    main()
