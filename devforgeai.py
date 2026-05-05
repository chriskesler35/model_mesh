#!/usr/bin/env python3
"""
DevForgeAI — CLI Runner
Usage:
    python devforgeai.py bootstrap      First-time setup (installer + guided config)
  python devforgeai.py start          Start both backend and frontend
  python devforgeai.py start backend  Start backend only
  python devforgeai.py start frontend Start frontend only
    python devforgeai.py sync           Refresh dependencies after git pull
  python devforgeai.py stop           Stop running servers
  python devforgeai.py status         Show server status
  python devforgeai.py install        Run the installer
"""

import os
import sys
import io
import signal

# Force UTF-8 output on Windows (avoids UnicodeEncodeError with symbols like → ✓ ✗)
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import subprocess
import platform
import time
import shutil
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
IS_WIN = platform.system() == "Windows"
ROOT_ENV_FILE = ROOT / ".env"
BACKEND_ENV_FILE = BACKEND_DIR / ".env"
BACKEND_ENV_EXAMPLE = BACKEND_DIR / ".env.example"

VENV_PYTHON = BACKEND_DIR / ("venv/Scripts/python.exe" if IS_WIN else "venv/bin/python")

PID_FILE = ROOT / ".devforgeai.pids"
LOCK_FILE = ROOT / ".devforgeai.start.lock"
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


def read_env_vars(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def append_env_var(path: Path, key: str, value: str):
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    if content and not content.endswith("\n"):
        content += "\n"
    content += f"{key}={value}\n"
    path.write_text(content, encoding="utf-8")


def ensure_backend_env_file() -> bool:
    if BACKEND_ENV_FILE.exists():
        return True

    if ROOT_ENV_FILE.exists():
        shutil.copy(ROOT_ENV_FILE, BACKEND_ENV_FILE)
        print(c(YELLOW, "  ⚠  backend/.env was missing. Copied values from root .env."))
        return True

    if BACKEND_ENV_EXAMPLE.exists():
        shutil.copy(BACKEND_ENV_EXAMPLE, BACKEND_ENV_FILE)
        print(c(YELLOW, "  ⚠  backend/.env was missing. Created from backend/.env.example."))
        return True

    return False


def migrate_legacy_env_keys(path: Path):
    if not path.exists():
        return
    values = read_env_vars(path)
    mappings = {
        "GITHUB_REDIRECT_URI": "GITHUB_OAUTH_REDIRECT_URL",
        "GOOGLE_REDIRECT_URI": "GOOGLE_OAUTH_REDIRECT_URL",
    }
    for old_key, new_key in mappings.items():
        if old_key in values and new_key not in values:
            append_env_var(path, new_key, values[old_key])
            print(c(YELLOW, f"  ⚠  Added {new_key} from legacy {old_key} in {path.name}."))


def run_checked(cmd, cwd=None):
    result = subprocess.run(cmd, cwd=cwd or ROOT)
    if result.returncode != 0:
        print(c(RED, f"  ✗  Command failed: {' '.join(cmd)}"))
        sys.exit(result.returncode)


def resolve_npm_command():
    for candidate in ("npm.cmd", "npm.exe", "npm"):
        npm = shutil.which(candidate)
        if npm:
            return npm
    return None


def read_pids():
    if PID_FILE.exists():
        try:
            pairs = PID_FILE.read_text().strip().splitlines()
            return {line.split("=")[0]: int(line.split("=")[1]) for line in pairs if "=" in line}
        except Exception:
            pass
    return {}


def acquire_start_lock() -> bool:
    if LOCK_FILE.exists():
        try:
            old_pid = int(LOCK_FILE.read_text().strip())
            if old_pid and is_alive(old_pid):
                return False
        except Exception:
            pass
        try:
            LOCK_FILE.unlink(missing_ok=True)
        except Exception:
            return False
    LOCK_FILE.write_text(str(os.getpid()))
    return True


def release_start_lock():
    try:
        LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def write_pids(pids: dict):
    PID_FILE.write_text("\n".join(f"{k}={v}" for k, v in pids.items()))


def list_listening_pids(port: int) -> list[int]:
    if not IS_WIN:
        return []
    result = subprocess.run(
        f'netstat -ano | findstr ":{port} " | findstr "LISTENING"',
        capture_output=True, text=True, shell=True,
    )
    if result.returncode != 0:
        return []
    pids = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if not parts:
            continue
        try:
            pids.append(int(parts[-1]))
        except ValueError:
            continue
    return sorted(set(pids))


def kill_listeners(port: int):
    for pid in list_listening_pids(port):
        kill_pid(pid)


def preflight_cleanup():
    # Enforce a single process set to avoid overlapping frontend/backend runtimes.
    pids = read_pids()
    for name in ("backend", "frontend"):
        pid = pids.get(name)
        if pid and is_alive(pid):
            kill_pid(pid)

    # Port-level cleanup catches orphans that don't belong to this PID file.
    for port in (3001, DEFAULT_BACKEND_PORT, FALLBACK_BACKEND_PORT):
        kill_listeners(port)

    time.sleep(1.5)


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


def _read_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if raw.isdigit():
        return int(raw)
    return default


def wait_for_http(url: str, timeout_sec: int = 120) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=4) as resp:
                if 200 <= resp.status < 500:
                    return True
        except urllib.error.HTTPError as exc:
            # Treat 4xx as "service is reachable" so startup checks only fail
            # when the server is unavailable or returns persistent 5xx errors.
            if 400 <= exc.code < 500:
                return True
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            pass
        time.sleep(1)
    return False


def start_backend():
    if not VENV_PYTHON.exists():
        print(c(RED, "  ✗  Virtual environment not found. Run: python install.py"))
        sys.exit(1)

    if not ensure_backend_env_file():
        print(c(RED, "  ✗  No .env file found and no template available to create one."))
        sys.exit(1)

    migrate_legacy_env_keys(BACKEND_ENV_FILE)

    env = os.environ.copy()

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
    npm = resolve_npm_command()
    if not npm:
        print(c(RED, "  ✗  npm not found. Install Node.js 18+ from https://nodejs.org/"))
        sys.exit(1)
    node_modules = FRONTEND_DIR / "node_modules"
    if not node_modules.exists():
        print(c(YELLOW, "  ⚠  node_modules missing. Running npm install..."))
        subprocess.run([npm, "install"], cwd=FRONTEND_DIR, check=True)

    print(f"  {CYAN}→{RESET}  Starting frontend on :3001 ...")
    env = os.environ.copy()
    env["DEVFORGEAI_BACKEND_PORT"] = str(backend_port)
    env["NEXT_PUBLIC_API_URL"] = f"http://localhost:{backend_port}"
    proc = subprocess.Popen(
        [npm, "run", "dev:clean"],
        cwd=FRONTEND_DIR,
        env=env,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if IS_WIN else 0,
    )
    return proc


def cmd_start(target=None):
    print(f"\n{BOLD}DevForgeAI — Starting{RESET}\n")

    if not acquire_start_lock():
        print(c(RED, "  ✗  Another DevForgeAI start command is already running."))
        print(c(YELLOW, "     If this is stale, delete .devforgeai.start.lock and retry."))
        sys.exit(1)

    preflight_cleanup()

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

    backend_ok = True
    frontend_ok = True
    backend_timeout_sec = _read_int_env("DEVFORGEAI_BACKEND_START_TIMEOUT", 120)
    frontend_timeout_sec = _read_int_env("DEVFORGEAI_FRONTEND_START_TIMEOUT", 90)
    if target in (None, "backend"):
        backend_ok = wait_for_http(
            f"http://127.0.0.1:{backend_port}/health",
            timeout_sec=backend_timeout_sec,
        )
    if target in (None, "frontend"):
        frontend_ok = wait_for_http(
            "http://127.0.0.1:3001",
            timeout_sec=frontend_timeout_sec,
        )

    if not backend_ok or not frontend_ok:
        print(c(RED, "\n  ✗  Startup health check failed."))
        if target in (None, "backend") and not backend_ok:
            print(c(RED, f"     Backend failed health check at http://127.0.0.1:{backend_port}/health"))
        if target in (None, "frontend") and not frontend_ok:
            print(c(RED, "     Frontend failed health check at http://127.0.0.1:3001"))
        for _, p in procs:
            kill_pid(p.pid)
        PID_FILE.unlink(missing_ok=True)
        release_start_lock()
        sys.exit(1)

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
        release_start_lock()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    if not IS_WIN:
        signal.signal(signal.SIGTERM, shutdown)

    try:
        for _, p in procs:
            p.wait()
    except KeyboardInterrupt:
        shutdown()
    finally:
        release_start_lock()


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


def cmd_bootstrap():
    print(f"\n{BOLD}DevForgeAI — Bootstrap{RESET}\n")
    install_script = ROOT / "install.py"
    if not install_script.exists():
        print(c(RED, "  install.py not found."))
        sys.exit(1)

    configure_flag = "--configure" if sys.stdin.isatty() else "--no-config"
    run_checked([sys.executable, str(install_script), configure_flag])


def cmd_sync():
    print(f"\n{BOLD}DevForgeAI — Sync (post-pull refresh){RESET}\n")

    if not VENV_PYTHON.exists():
        print(c(RED, "  ✗  backend/venv is missing. Run: python devforgeai.py bootstrap"))
        sys.exit(1)

    print(f"  {CYAN}→{RESET}  Updating backend dependencies...")
    run_checked([str(VENV_PYTHON), "-m", "pip", "install", "--upgrade", "pip"], cwd=BACKEND_DIR)
    run_checked([str(VENV_PYTHON), "-m", "pip", "install", "-r", "requirements.txt"], cwd=BACKEND_DIR)

    print(f"  {CYAN}→{RESET}  Updating frontend dependencies...")
    npm = resolve_npm_command()
    if not npm:
        print(c(RED, "  ✗  npm not found. Install Node.js 18+ from https://nodejs.org/"))
        sys.exit(1)
    run_checked([npm, "install", "--loglevel=error"], cwd=FRONTEND_DIR)

    if ensure_backend_env_file():
        migrate_legacy_env_keys(BACKEND_ENV_FILE)

    print(c(GREEN, "\n  ✓  Sync complete. You can now run: python devforgeai.py start\n"))


def usage():
    print(f"""
{BOLD}DevForgeAI CLI{RESET}

    {CYAN}python devforgeai.py bootstrap{RESET}       First-time guided setup
  {CYAN}python devforgeai.py start{RESET}           Start backend + frontend
  {CYAN}python devforgeai.py start backend{RESET}   Start backend only
  {CYAN}python devforgeai.py start frontend{RESET}  Start frontend only
    {CYAN}python devforgeai.py sync{RESET}            Post-pull dependency refresh
  {CYAN}python devforgeai.py stop{RESET}            Stop running servers
  {CYAN}python devforgeai.py status{RESET}          Show server status
  {CYAN}python devforgeai.py install{RESET}         Run the installer
""")


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help", "help"):
        usage()
    elif args[0] == "bootstrap":
        cmd_bootstrap()
    elif args[0] == "start":
        target = args[1] if len(args) > 1 else None
        cmd_start(target)
    elif args[0] == "sync":
        cmd_sync()
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
