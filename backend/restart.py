"""Restart helper — waits for port to be free, then starts uvicorn."""
import sys
import time
import socket
import subprocess
import os
from pathlib import Path

PORT = 19000
BACKEND_DIR = str(Path(__file__).parent)

# Always use the venv Python
if sys.platform == "win32":
    PYTHON = str(Path(BACKEND_DIR) / "venv" / "Scripts" / "python.exe")
else:
    PYTHON = str(Path(BACKEND_DIR) / "venv" / "bin" / "python")

if not Path(PYTHON).exists():
    PYTHON = sys.executable

def port_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) != 0

# Wait for the old process to release the port (up to 15s)
for i in range(30):
    if port_free(PORT):
        break
    time.sleep(0.5)

if not port_free(PORT):
    # Force kill whatever is on the port
    if sys.platform == "win32":
        os.system(f'for /f "tokens=5" %a in (\'netstat -ano ^| findstr ":{PORT} " ^| findstr "LISTENING"\') do taskkill /PID %a /F')
    time.sleep(2)

# Start uvicorn — use START on Windows for a proper detached window
if sys.platform == "win32":
    os.system(f'start "DevForgeAI Backend" /MIN /D "{BACKEND_DIR}" "{PYTHON}" -m uvicorn app.main:app --host 0.0.0.0 --port {PORT}')
else:
    subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", str(PORT)],
        cwd=BACKEND_DIR,
        start_new_session=True,
    )
