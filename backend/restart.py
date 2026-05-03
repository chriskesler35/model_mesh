"""Restart helper — force-cleans stale listeners, then starts uvicorn fresh."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.resolve()


def _resolve_backend_port() -> int:
    raw = (os.environ.get("DEVFORGEAI_BACKEND_PORT", "") or "").strip()
    if raw.isdigit():
        return int(raw)
    return 19001


TARGET_PORT = _resolve_backend_port()
PORTS_TO_CLEAN = sorted(set([19000, 19001, TARGET_PORT]))

# Always use backend venv python when available.
if sys.platform == "win32":
    PYTHON = BACKEND_DIR / "venv" / "Scripts" / "python.exe"
else:
    PYTHON = BACKEND_DIR / "venv" / "bin" / "python"
if not PYTHON.exists():
    PYTHON = Path(sys.executable)


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def _list_listening_pids(port: int) -> list[int]:
    if sys.platform != "win32":
        return []
    result = subprocess.run(
        f'netstat -ano | findstr ":{port} " | findstr "LISTENING"',
        capture_output=True,
        text=True,
        shell=True,
    )
    if result.returncode != 0:
        return []
    pids: list[int] = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if not parts:
            continue
        try:
            pids.append(int(parts[-1]))
        except ValueError:
            continue
    return sorted(set(pids))


def _kill_pid(pid: int):
    try:
        if sys.platform == "win32":
            subprocess.run(f"taskkill /PID {pid} /F /T", shell=True, capture_output=True)
        else:
            os.kill(pid, 9)
    except Exception:
        pass


# Kill stale listeners on both backend ports so restart always picks up latest code.
for _port in PORTS_TO_CLEAN:
    for _pid in _list_listening_pids(_port):
        _kill_pid(_pid)

# Wait for target port to free before restart.
for _ in range(40):
    if _port_free(TARGET_PORT):
        break
    time.sleep(0.25)

# Start uvicorn detached on the resolved backend port.
if sys.platform == "win32":
    subprocess.Popen(
        [str(PYTHON), "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", str(TARGET_PORT)],
        cwd=str(BACKEND_DIR),
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "DEVFORGEAI_BACKEND_PORT": str(TARGET_PORT)},
    )
else:
    subprocess.Popen(
        [str(PYTHON), "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", str(TARGET_PORT)],
        cwd=str(BACKEND_DIR),
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "DEVFORGEAI_BACKEND_PORT": str(TARGET_PORT)},
    )
