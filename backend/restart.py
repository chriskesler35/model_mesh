"""Restart helper — waits for port to be free, then starts uvicorn."""
import sys
import time
import socket
import subprocess
from pathlib import Path

PORT = 19000
BACKEND_DIR = str(Path(__file__).parent)

# Always use the venv Python, not whatever sys.executable is
VENV_PYTHON = str(Path(BACKEND_DIR) / "venv" / "Scripts" / "python.exe")
if not Path(VENV_PYTHON).exists():
    # Linux/macOS fallback
    VENV_PYTHON = str(Path(BACKEND_DIR) / "venv" / "bin" / "python")
if not Path(VENV_PYTHON).exists():
    # Last resort — use whatever called us
    VENV_PYTHON = sys.executable
PYTHON = VENV_PYTHON

def port_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) != 0

# Wait for the old process to release the port (up to 10s)
for i in range(20):
    if port_free(PORT):
        break
    time.sleep(0.5)

# Start uvicorn
subprocess.Popen(
    [PYTHON, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", str(PORT)],
    cwd=BACKEND_DIR,
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
)
