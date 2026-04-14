#!/usr/bin/env python3
"""
DevForgeAI — CLI Runner
Usage:
  python devforgeai.py start          Start both backend and frontend
  python devforgeai.py start backend  Start backend only
  python devforgeai.py start frontend Start frontend only
  python devforgeai.py stop           Stop running servers
  python devforgeai.py status         Show server status
  python devforgeai.py install        Run the installer
"""

import os
import sys
import signal
import subprocess
import platform
import time
import shutil
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
IS_WIN = platform.system() == "Windows"

VENV_PYTHON = BACKEND_DIR / ("venv/Scripts/python.exe" if IS_WIN else "venv/bin/python")

PID_FILE = ROOT / ".devforgeai.pids"
DEFAULT_BACKEND_PORT = 19001
FALLBACK_BACKEND_PORT = 19000

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"


def c(col, text):
    return f"{col}{text}{RESET}"


def read_pids():
    if PID_FILE.exists():
        try:
            pairs = PID_FILE.read_text().strip().splitlines()
            return {line.split("=")[0]: int(line.split("=")[1]) for line in pairs if "=" in line}
        except Exception:
            pass
    return {}


def write_pids(pids: dict):
    PID_FILE.write_text("\n".join(f"{k}={v}" for k, v in pids.items()))


def is_alive(pid):
    try:
        if IS_WIN:
            result = subprocess.run(
                f"tasklist /FI \"PID eq {pid}\" /FO CSV /NH",
                capture_output=True, text=True, shell=True
            )
            return str(pid) in result.stdout
        else:
            os.kill(pid, 0)
            return True
    except (ProcessLookupError, PermissionError):
        return False


def kill_pid(pid):
    try:
        if IS_WIN:
            subprocess.run(f"taskkill /PID {pid} /F /T", shell=True,
                           capture_output=True)
        else:
            os.kill(pid, signal.SIGTERM)
    except Exception:
        pass


def is_port_listening(port: int) -> bool:
    if IS_WIN:
        result = subprocess.run(
            f'netstat -ano | findstr ":{port} " | findstr "LISTENING"',
            capture_output=True, text=True, shell=True,
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    return False


def resolve_backend_port() -> int:
    configured = os.environ.get("DEVFORGEAI_BACKEND_PORT", "").strip()
    if configured.isdigit():
        return int(configured)
    if IS_WIN and is_port_listening(DEFAULT_BACKEND_PORT):
        return FALLBACK_BACKEND_PORT
    return DEFAULT_BACKEND_PORT


def start_backend():
    if not VENV_PYTHON.exists():
        print(c(RED, "  ✗  Virtual environment not found. Run: python install.py"))
        sys.exit(1)
    env = os.environ.copy()
    env_file = BACKEND_DIR / ".env"
    if not env_file.exists():
        print(c(YELLOW, f"  ⚠  No .env file found at {env_file}"))
        print(c(YELLOW, "     Copy backend/.env.example → backend/.env and add API keys."))
        sys.exit(1)

    backend_port = resolve_backend_port()
    env["DEVFORGEAI_BACKEND_PORT"] = str(backend_port)

    print(f"  {CYAN}→{RESET}  Starting backend on :{backend_port} ...")
    proc = subprocess.Popen(
        [str(VENV_PYTHON), "-m", "uvicorn", "app.main:app",
         "--host", "0.0.0.0", "--port", str(backend_port), "--reload"],
        cwd=BACKEND_DIR,
        env=env,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if IS_WIN else 0,
    )
    return proc, backend_port


def start_frontend(backend_port: int):
    npm = shutil.which("npm")
    if not npm:
        print(c(RED, "  ✗  npm not found. Install Node.js 18+ from https://nodejs.org/"))
        sys.exit(1)
    node_modules = FRONTEND_DIR / "node_modules"
    if not node_modules.exists():
        print(c(YELLOW, "  ⚠  node_modules missing. Running npm install..."))
        subprocess.run("npm install", cwd=FRONTEND_DIR, shell=True, check=True)

    print(f"  {CYAN}→{RESET}  Starting frontend on :3001 ...")
    env = os.environ.copy()
    env["DEVFORGEAI_BACKEND_PORT"] = str(backend_port)
    env["NEXT_PUBLIC_API_URL"] = f"http://localhost:{backend_port}"
    proc = subprocess.Popen(
        "npm run dev",
        cwd=FRONTEND_DIR,
        shell=True,
        env=env,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if IS_WIN else 0,
    )
    return proc


def cmd_start(target=None):
    print(f"\n{BOLD}DevForgeAI — Starting{RESET}\n")

    pids = {}
    procs = []
    backend_port = resolve_backend_port()

    if target in (None, "backend"):
        p, backend_port = start_backend()
        pids["backend"] = p.pid
        pids["backend_port"] = backend_port
        procs.append(("backend", p))

    if target in (None, "frontend"):
        p = start_frontend(backend_port)
        pids["frontend"] = p.pid
        procs.append(("frontend", p))

    write_pids(pids)
    time.sleep(2)

    print(f"""
  {GREEN}{BOLD}Running!{RESET}

    Frontend  →  {CYAN}http://localhost:3001{RESET}
        Backend   →  {CYAN}http://localhost:{backend_port}{RESET}
        API Docs  →  {CYAN}http://localhost:{backend_port}/docs{RESET}

  Press {BOLD}Ctrl+C{RESET} to stop.
""")

    def shutdown(sig=None, frame=None):
        print(f"\n  {YELLOW}Shutting down...{RESET}")
        for name, p in procs:
            kill_pid(p.pid)
            print(f"  {CYAN}→{RESET}  Stopped {name}")
        PID_FILE.unlink(missing_ok=True)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    if not IS_WIN:
        signal.signal(signal.SIGTERM, shutdown)

    try:
        for _, p in procs:
            p.wait()
    except KeyboardInterrupt:
        shutdown()


def cmd_stop():
    print(f"\n{BOLD}DevForgeAI — Stopping{RESET}\n")
    pids = read_pids()
    if not pids:
        print(c(YELLOW, "  No running processes found."))
        return
    for name, pid in pids.items():
        if is_alive(pid):
            kill_pid(pid)
            print(f"  {GREEN}✓{RESET}  Stopped {name} (PID {pid})")
        else:
            print(f"  {YELLOW}⚠{RESET}  {name} was not running")
    PID_FILE.unlink(missing_ok=True)
    print()


def cmd_status():
    print(f"\n{BOLD}DevForgeAI — Status{RESET}\n")
    pids = read_pids()

    def check(name, pid=None):
        if pid and is_alive(pid):
            print(f"  {GREEN}●{RESET}  {name:<12} running  (PID {pid})")
        else:
            print(f"  {RED}○{RESET}  {name:<12} stopped")

    check("backend", pids.get("backend"))
    check("frontend", pids.get("frontend"))
    print()


def cmd_install():
    install_script = ROOT / "install.py"
    if install_script.exists():
        subprocess.run([sys.executable, str(install_script)], check=True)
    else:
        print(c(RED, "  install.py not found."))
        sys.exit(1)


def usage():
    print(f"""
{BOLD}DevForgeAI CLI{RESET}

  {CYAN}python devforgeai.py start{RESET}           Start backend + frontend
  {CYAN}python devforgeai.py start backend{RESET}   Start backend only
  {CYAN}python devforgeai.py start frontend{RESET}  Start frontend only
  {CYAN}python devforgeai.py stop{RESET}            Stop running servers
  {CYAN}python devforgeai.py status{RESET}          Show server status
  {CYAN}python devforgeai.py install{RESET}         Run the installer
""")


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help", "help"):
        usage()
    elif args[0] == "start":
        target = args[1] if len(args) > 1 else None
        cmd_start(target)
    elif args[0] == "stop":
        cmd_stop()
    elif args[0] == "status":
        cmd_status()
    elif args[0] == "install":
        cmd_install()
    else:
        print(c(RED, f"  Unknown command: {args[0]}"))
        usage()
        sys.exit(1)
