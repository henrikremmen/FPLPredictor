"""Start the local FastAPI service and React development server."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parent


def commands() -> tuple[list[str], list[str]]:
    npm = shutil.which("npm")
    if npm is None:
        raise RuntimeError("npm ble ikke funnet. Installer Node.js 20 eller nyere først.")
    if not (ROOT / "frontend" / "node_modules").exists():
        raise RuntimeError("Frontend-pakker mangler. Kjør: npm install --prefix frontend")
    backend = [
        sys.executable, "-m", "uvicorn", "api:app", "--app-dir", str(ROOT / "src"),
        "--host", "127.0.0.1", "--port", "8000",
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
        backend, frontend = commands()
    except RuntimeError as exc:
        print(f"Feil: {exc}", file=sys.stderr)
        return 1

    print("Starter FPL Modell på http://127.0.0.1:5173")
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
