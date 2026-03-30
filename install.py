#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DevForgeAI -- Cross-Platform Installer
Supports Windows, macOS, and Linux.
Run: python install.py
"""

import os
import sys
import shutil
import subprocess
import platform
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
DATA_DIR = ROOT / "data"
ENV_FILE = BACKEND_DIR / ".env"
ENV_EXAMPLE = BACKEND_DIR / ".env.example"

OS = platform.system()  # "Windows", "Darwin", "Linux"
IS_WIN = OS == "Windows"
IS_MAC = OS == "Darwin"
IS_LINUX = OS == "Linux"

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"


def c(color, text):
    return f"{color}{text}{RESET}"


def header(text):
    print(f"\n{BOLD}{CYAN}{'='*60}{RESET}")
    print(f"{BOLD}{CYAN}  {text}{RESET}")
    print(f"{BOLD}{CYAN}{'='*60}{RESET}")


def ok(text):
    print(f"  {GREEN}✓{RESET}  {text}")


def warn(text):
    print(f"  {YELLOW}⚠{RESET}  {text}")


def err(text):
    print(f"  {RED}✗{RESET}  {text}")


def info(text):
    print(f"  {CYAN}→{RESET}  {text}")


def run(cmd, cwd=None, check=True, capture=False):
    kwargs = dict(cwd=cwd or ROOT, shell=True)
    if capture:
        kwargs["capture_output"] = True
        kwargs["text"] = True
    result = subprocess.run(cmd, **kwargs)
    if check and result.returncode != 0:
        err(f"Command failed: {cmd}")
        sys.exit(1)
    return result


def check_python():
    header("Checking Python")
    version = sys.version_info
    if version < (3, 11):
        err(f"Python 3.11+ required. Found: {sys.version}")
        sys.exit(1)
    ok(f"Python {version.major}.{version.minor}.{version.micro}")


def check_node():
    header("Checking Node.js")
    if not shutil.which("node"):
        err("Node.js not found.")
        print("""
  Install Node.js 18+ from: https://nodejs.org/
  Then re-run this installer.
""")
        sys.exit(1)

    result = run("node --version", capture=True)
    node_ver = result.stdout.strip()
    major = int(node_ver.lstrip("v").split(".")[0])
    if major < 18:
        err(f"Node.js 18+ required. Found: {node_ver}")
        sys.exit(1)
    ok(f"Node.js {node_ver}")

    if shutil.which("npm"):
        result = run("npm --version", capture=True)
        ok(f"npm {result.stdout.strip()}")
    else:
        err("npm not found. Please reinstall Node.js.")
        sys.exit(1)


def install_backend():
    header("Installing Backend (Python)")

    venv_dir = BACKEND_DIR / "venv"
    python_bin = venv_dir / ("Scripts/python.exe" if IS_WIN else "bin/python")

    if not venv_dir.exists():
        info("Creating virtual environment...")
        run(f'"{sys.executable}" -m venv "{venv_dir}"')
        ok("Virtual environment created")
    else:
        ok("Virtual environment already exists")

    info("Installing Python dependencies...")
    pip_cmd = f'"{python_bin}" -m pip install --upgrade pip -q'
    run(pip_cmd)

    req_file = BACKEND_DIR / "requirements.txt"
    run(f'"{python_bin}" -m pip install -r "{req_file}" -q')
    ok("Python dependencies installed")

    return python_bin


def install_frontend():
    header("Installing Frontend (Node.js)")
    info("Installing npm packages (this may take a minute)...")
    run("npm install --loglevel=error", cwd=FRONTEND_DIR)
    ok("Frontend dependencies installed")


def setup_env():
    header("Setting Up Environment")

    DATA_DIR.mkdir(exist_ok=True)
    ok("data/ directory ready")

    if ENV_FILE.exists():
        ok(".env already exists — skipping (edit manually if needed)")
        return

    if ENV_EXAMPLE.exists():
        shutil.copy(ENV_EXAMPLE, ENV_FILE)
        ok(f".env created from .env.example")
    else:
        # Write a minimal .env
        ENV_FILE.write_text(
            "DATABASE_URL=\n"
            "ANTHROPIC_API_KEY=\n"
            "GOOGLE_API_KEY=\n"
            "GEMINI_API_KEY=\n"
            "OPENROUTER_API_KEY=\n"
            "OPENAI_API_KEY=\n"
            "OLLAMA_BASE_URL=http://localhost:11434\n"
            "COMFYUI_URL=http://localhost:8188\n"
            "MODELMESH_API_KEY=modelmesh_local_dev_key\n"
            "TELEGRAM_BOT_TOKEN=\n"
            "TELEGRAM_CHAT_IDS=\n"
        )
        ok(".env created")

    warn(f"Edit {ENV_FILE} and add at least one AI provider API key.")


def create_start_scripts(python_bin):
    header("Creating Start Scripts")

    if IS_WIN:
        bat = ROOT / "start.bat"
        bat.write_text(
            f'@echo off\n'
            f'echo Starting DevForgeAI...\n'
            f'echo.\n'
            f'start "DevForgeAI Backend" cmd /k "cd /d "{BACKEND_DIR}" && "{python_bin}" -m uvicorn app.main:app --host 0.0.0.0 --port 19000 --reload"\n'
            f'timeout /t 3 /nobreak >nul\n'
            f'start "DevForgeAI Frontend" cmd /k "cd /d "{FRONTEND_DIR}" && npm run dev"\n'
            f'echo.\n'
            f'echo Backend:  http://localhost:19000\n'
            f'echo Frontend: http://localhost:3001\n'
            f'echo API Docs: http://localhost:19000/docs\n'
            f'echo.\n'
            f'pause\n'
        )
        ok(f"Created start.bat")

    else:
        sh = ROOT / "start.sh"
        sh.write_text(
            f'#!/usr/bin/env bash\n'
            f'set -e\n'
            f'cd "{ROOT}"\n\n'
            f'echo "Starting DevForgeAI Backend on :19000..."\n'
            f'cd backend\n'
            f'source venv/bin/activate\n'
            f'uvicorn app.main:app --host 0.0.0.0 --port 19000 --reload &\n'
            f'BACKEND_PID=$!\n\n'
            f'echo "Starting DevForgeAI Frontend on :3001..."\n'
            f'cd "{FRONTEND_DIR}"\n'
            f'npm run dev &\n'
            f'FRONTEND_PID=$!\n\n'
            f'echo ""\n'
            f'echo "  Backend:  http://localhost:19000"\n'
            f'echo "  Frontend: http://localhost:3001"\n'
            f'echo "  API Docs: http://localhost:19000/docs"\n'
            f'echo ""\n'
            f'echo "Press Ctrl+C to stop both servers."\n'
            f'trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM\n'
            f'wait\n'
        )
        sh.chmod(0o755)
        ok("Created start.sh")


def print_summary(python_bin):
    header("Installation Complete!")
    print(f"""
  {GREEN}{BOLD}DevForgeAI is ready.{RESET}

  {BOLD}Next steps:{RESET}

    1. Add at least one API key to:
       {YELLOW}{ENV_FILE}{RESET}

    2. Start the app:
""")
    if IS_WIN:
        print(f"       {CYAN}Double-click start.bat{RESET}  — or —")
        print(f"       {CYAN}python devforgeai.py start{RESET}")
    else:
        print(f"       {CYAN}./start.sh{RESET}  — or —")
        print(f"       {CYAN}python devforgeai.py start{RESET}")

    print(f"""
    3. Open your browser:
       {CYAN}http://localhost:3001{RESET}

  {BOLD}URLs:{RESET}
    Frontend  →  http://localhost:3001
    Backend   →  http://localhost:19000
    API Docs  →  http://localhost:19000/docs

  {BOLD}Supported AI Providers:{RESET}
    Ollama (local, no key), Anthropic, Google Gemini,
    OpenRouter, OpenAI

  {BOLD}Docs:{RESET} INSTALL.md
""")


def main():
    print(f"""
{BOLD}{CYAN}
  DevForgeAI
  ----------
  AI Development Platform
{RESET}
  {BOLD}Installer -- {OS}{RESET}
""")

    check_python()
    check_node()
    python_bin = install_backend()
    install_frontend()
    setup_env()
    create_start_scripts(python_bin)
    print_summary(python_bin)


if __name__ == "__main__":
    main()
