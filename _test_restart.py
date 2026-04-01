from pathlib import Path
import subprocess, sys

venv_python = Path("G:/Model_Mesh/backend/venv/Scripts/python.exe")
print(f"Venv python exists: {venv_python.exists()}")

# Test uvicorn import
result = subprocess.run(
    [str(venv_python), "-c", "import uvicorn; print('uvicorn OK')"],
    capture_output=True, text=True, timeout=10
)
print(f"Import test: {result.stdout.strip()} | {result.stderr.strip()[:200]}")

# Now actually try starting uvicorn and see what happens
print("Starting uvicorn...")
proc = subprocess.Popen(
    [str(venv_python), "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "19000"],
    cwd="G:/Model_Mesh/backend",
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)
import time
time.sleep(10)

# Check if it's still running
if proc.poll() is None:
    print(f"Process running! PID: {proc.pid}")
else:
    print(f"Process DIED with code: {proc.returncode}")
    print(f"stdout: {proc.stdout.read().decode()[:500]}")
    print(f"stderr: {proc.stderr.read().decode()[:500]}")
