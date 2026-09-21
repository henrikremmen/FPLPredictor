"""Start the local FastAPI service and React development server."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

# Piping/redirecting stdout (nohup, a log file, a background job) switches
# Python to full buffering, so status prints below — especially the LAN IP
# hint a user needs right away to configure the mobile app — can sit
# invisible in the buffer until the process exits. Force line buffering so
# they show up immediately regardless of how this is run.
sys.stdout.reconfigure(line_buffering=True)

ROOT = Path(__file__).resolve().parent
HOST = os.environ.get("FPL_API_HOST", "127.0.0.1")
BACKEND_PORT = int(os.environ.get("FPL_API_PORT", "8000"))
FRONTEND_PORT = int(os.environ.get("FPL_FRONTEND_PORT", "5173"))
CHECK_HOST = "127.0.0.1" if HOST == "0.0.0.0" else HOST


def lan_ip() -> str | None:
    """Best-effort local network IP, for pointing a phone at this machine."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.connect(("8.8.8.8", 80))
            return probe.getsockname()[0]
        except OSError:
            return None


def url_responds(url: str) -> bool:
    """Return whether a local service responds, including with an HTTP error."""
    try:
        with urlopen(url, timeout=0.75):
            return True
    except HTTPError:
        return True
    except (URLError, TimeoutError):
        return False


def port_is_busy(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.settimeout(0.25)
        return connection.connect_ex((CHECK_HOST, port)) == 0


def check_existing_app() -> bool:
    """Avoid starting duplicate frontend/backend pairs on new ports."""
    backend_ready = url_responds(f"http://{CHECK_HOST}:{BACKEND_PORT}/api/health")
    frontend_ready = url_responds(f"http://{CHECK_HOST}:{FRONTEND_PORT}/")
    if backend_ready and frontend_ready:
        print(f"FPL Modell kjører allerede på http://{CHECK_HOST}:{FRONTEND_PORT}")
        return True

    busy = [port for port in (BACKEND_PORT, FRONTEND_PORT) if port_is_busy(port)]
    if busy:
        ports = ", ".join(str(port) for port in busy)
        raise RuntimeError(
            f"Port {ports} er allerede i bruk, men appen svarer ikke komplett. "
            "Stopp den gamle terminalprosessen med Ctrl+C og prøv igjen."
        )
    return False


def commands() -> tuple[list[str], list[str]]:
    npm = shutil.which("npm")
    if npm is None:
        raise RuntimeError("npm ble ikke funnet. Installer Node.js 20 eller nyere først.")
    if not (ROOT / "frontend" / "node_modules").exists():
        raise RuntimeError("Frontend-pakker mangler. Kjør: npm install --prefix frontend")
    backend = [
        sys.executable, "-m", "uvicorn", "api:app", "--app-dir", str(ROOT / "src"),
        "--host", HOST, "--port", str(BACKEND_PORT),
    ]
    frontend = [npm, "--prefix", str(ROOT / "frontend"), "run", "dev"]
    return backend, frontend


def stop(processes: list[subprocess.Popen]) -> None:
    for process in processes:
        if process.poll() is None:
            process.terminate()
    deadline = time.monotonic() + 4
    for process in processes:
        remaining = max(0, deadline - time.monotonic())
        try:
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def main() -> int:
    try:
        if check_existing_app():
            return 0
        backend, frontend = commands()
    except RuntimeError as exc:
        print(f"Feil: {exc}", file=sys.stderr)
        return 1

    print(f"Starter FPL Modell på http://{CHECK_HOST}:{FRONTEND_PORT}")
    if HOST == "0.0.0.0":
        ip = lan_ip()
        print(f"Backend lytter på alle nettverk (0.0.0.0:{BACKEND_PORT}).")
        if ip:
            print(
                f"Fra en iPhone på samme Wi-Fi, sett apps/mobile/.env til "
                f"EXPO_PUBLIC_API_URL=http://{ip}:{BACKEND_PORT}"
            )
        else:
            print("Fant ikke lokal IP automatisk; kjør `ipconfig getifaddr en0` for å finne den.")
    processes: list[subprocess.Popen] = []
    try:
        processes.append(subprocess.Popen(backend, cwd=ROOT))
        processes.append(subprocess.Popen(frontend, cwd=ROOT))
        while all(process.poll() is None for process in processes):
            time.sleep(.25)
        failed = next((process.returncode for process in processes if process.returncode), 0)
        return int(failed or 0)
    except KeyboardInterrupt:
        return 0
    finally:
        stop(processes)


if __name__ == "__main__":
    raise SystemExit(main())
