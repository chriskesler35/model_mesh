#!/usr/bin/env python3
"""
DevForgeAI -- Cross-Platform Installer
Supports Windows, macOS, and Linux.
Run: python install.py
"""

import argparse
import platform
import shutil
import subprocess
import sys
from getpass import getpass
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).parent.resolve()
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
DATA_DIR = ROOT / "data"
LOGS_DIR = ROOT / "logs"
ENV_FILE = BACKEND_DIR / ".env"
ENV_EXAMPLE = BACKEND_DIR / ".env.example"

OS = platform.system()  # "Windows", "Darwin", "Linux"
IS_WIN = OS == "Windows"

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"


def header(text: str):
    print(f"\n{BOLD}{CYAN}{'=' * 60}{RESET}")
    print(f"{BOLD}{CYAN}  {text}{RESET}")
    print(f"{BOLD}{CYAN}{'=' * 60}{RESET}")


def ok(text: str):
    print(f"  {GREEN}OK{RESET}  {text}")


def warn(text: str):
    print(f"  {YELLOW}WARN{RESET}  {text}")


def err(text: str):
    print(f"  {RED}ERR{RESET}  {text}")


def info(text: str):
    print(f"  {CYAN}->{RESET}  {text}")


def run(cmd: str, cwd: Path | None = None, check: bool = True, capture: bool = False):
    kwargs = dict(cwd=cwd or ROOT, shell=True)
    if capture:
        kwargs["capture_output"] = True
        kwargs["text"] = True
    result = subprocess.run(cmd, **kwargs)
    if check and result.returncode != 0:
        err(f"Command failed: {cmd}")
        sys.exit(1)
    return result


def parse_args():
    parser = argparse.ArgumentParser(description="Install DevForgeAI")
    parser.add_argument("--configure", action="store_true", help="Run guided configuration walkthrough")
    parser.add_argument("--no-config", action="store_true", help="Skip guided configuration walkthrough")
    parser.add_argument("--non-interactive", action="store_true", help="Do not prompt; normalize env defaults")
    return parser.parse_args()


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
        err("Node.js not found. Install Node.js 18+ from https://nodejs.org/")
        sys.exit(1)

    node_result = run("node --version", capture=True)
    node_ver = node_result.stdout.strip()
    major = int(node_ver.lstrip("v").split(".")[0])
    if major < 18:
        err(f"Node.js 18+ required. Found: {node_ver}")
        sys.exit(1)
    ok(f"Node.js {node_ver}")

    if not shutil.which("npm"):
        err("npm not found. Reinstall Node.js.")
        sys.exit(1)
    npm_result = run("npm --version", capture=True)
    ok(f"npm {npm_result.stdout.strip()}")


def install_backend() -> Path:
    header("Installing Backend (Python)")

    venv_dir = BACKEND_DIR / "venv"
    python_bin = venv_dir / ("Scripts/python.exe" if IS_WIN else "bin/python")

    if not venv_dir.exists():
        info("Creating virtual environment...")
        run(f'"{sys.executable}" -m venv "{venv_dir}"')
        ok("Virtual environment created")
    else:
        ok("Virtual environment already exists")

    info("Installing backend dependencies...")
    run(f'"{python_bin}" -m pip install --upgrade pip')
    run(f'"{python_bin}" -m pip install -r "{BACKEND_DIR / "requirements.txt"}"')
    ok("Backend dependencies installed")

    return python_bin


def install_frontend():
    header("Installing Frontend (Node.js)")
    info("Installing frontend dependencies...")
    run("npm install --loglevel=error", cwd=FRONTEND_DIR)
    ok("Frontend dependencies installed")


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


def normalize_env(values: dict[str, str]) -> dict[str, str]:
    if values.get("GITHUB_REDIRECT_URI") and not values.get("GITHUB_OAUTH_REDIRECT_URL"):
        values["GITHUB_OAUTH_REDIRECT_URL"] = values["GITHUB_REDIRECT_URI"]
    if values.get("GOOGLE_REDIRECT_URI") and not values.get("GOOGLE_OAUTH_REDIRECT_URL"):
        values["GOOGLE_OAUTH_REDIRECT_URL"] = values["GOOGLE_REDIRECT_URI"]
    return values


def write_env_vars(path: Path, values: dict[str, str]):
    ordered_keys = [
        "DATABASE_URL",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "OPENROUTER_API_KEY",
        "OPENAI_API_KEY",
        "OLLAMA_BASE_URL",
        "COMFYUI_URL",
        "MODELMESH_API_KEY",
        "GITHUB_CLIENT_ID",
        "GITHUB_CLIENT_SECRET",
        "GITHUB_OAUTH_REDIRECT_URL",
        "GOOGLE_OAUTH_CLIENT_ID",
        "GOOGLE_OAUTH_CLIENT_SECRET",
        "GOOGLE_OAUTH_REDIRECT_URL",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_IDS",
    ]

    lines = [
        "# DevForgeAI environment values",
        "# Generated/updated by install.py",
        "",
    ]
    for key in ordered_keys:
        lines.append(f"{key}={values.get(key, '')}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def setup_env():
    header("Setting Up Environment")

    DATA_DIR.mkdir(exist_ok=True)
    LOGS_DIR.mkdir(exist_ok=True)
    ok("data/ and logs/ directories ready")

    if ENV_FILE.exists():
        ok("backend/.env already exists")
        return

    if ENV_EXAMPLE.exists():
        shutil.copy(ENV_EXAMPLE, ENV_FILE)
        ok("Created backend/.env from backend/.env.example")
    else:
        values = {
            "DATABASE_URL": "",
            "ANTHROPIC_API_KEY": "",
            "GOOGLE_API_KEY": "",
            "GEMINI_API_KEY": "",
            "OPENROUTER_API_KEY": "",
            "OPENAI_API_KEY": "",
            "OLLAMA_BASE_URL": "http://localhost:11434",
            "COMFYUI_URL": "http://localhost:8188",
            "MODELMESH_API_KEY": "modelmesh_local_dev_key",
            "GITHUB_CLIENT_ID": "",
            "GITHUB_CLIENT_SECRET": "",
            "GITHUB_OAUTH_REDIRECT_URL": "http://localhost:3001/auth/github/callback",
            "GOOGLE_OAUTH_CLIENT_ID": "",
            "GOOGLE_OAUTH_CLIENT_SECRET": "",
            "GOOGLE_OAUTH_REDIRECT_URL": "http://localhost:3001/auth/google/callback",
            "TELEGRAM_BOT_TOKEN": "",
            "TELEGRAM_CHAT_IDS": "",
        }
        write_env_vars(ENV_FILE, values)
        ok("Created backend/.env with defaults")


def prompt_yes_no(prompt: str, default: bool = True) -> bool:
    if not sys.stdin.isatty():
        return default

    hint = "Y/n" if default else "y/N"
    while True:
        answer = input(f"{prompt} [{hint}]: ").strip().lower()
        if not answer:
            return default
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        print("Please enter y or n.")


def prompt_value(label: str, current: str = "", secret: bool = False) -> str:
    if not sys.stdin.isatty():
        return current

    suffix = " (press Enter to keep current)" if current else " (optional)"
    if secret:
        value = getpass(f"{label}{suffix}: ").strip()
    else:
        value = input(f"{label}{suffix}: ").strip()
    return value if value else current


def check_ollama(base_url: str) -> bool:
    if not base_url:
        return False
    url = base_url.rstrip("/") + "/api/tags"
    try:
        with urlopen(url, timeout=3) as resp:
            return 200 <= resp.status < 500
    except Exception:
        return False


def configure_env_walkthrough(non_interactive: bool = False):
    header("Configuration Walkthrough")

    defaults = {
        "DATABASE_URL": "",
        "ANTHROPIC_API_KEY": "",
        "GOOGLE_API_KEY": "",
        "GEMINI_API_KEY": "",
        "OPENROUTER_API_KEY": "",
        "OPENAI_API_KEY": "",
        "OLLAMA_BASE_URL": "http://localhost:11434",
        "COMFYUI_URL": "http://localhost:8188",
        "MODELMESH_API_KEY": "modelmesh_local_dev_key",
        "GITHUB_CLIENT_ID": "",
        "GITHUB_CLIENT_SECRET": "",
        "GITHUB_OAUTH_REDIRECT_URL": "http://localhost:3001/auth/github/callback",
        "GOOGLE_OAUTH_CLIENT_ID": "",
        "GOOGLE_OAUTH_CLIENT_SECRET": "",
        "GOOGLE_OAUTH_REDIRECT_URL": "http://localhost:3001/auth/google/callback",
        "TELEGRAM_BOT_TOKEN": "",
        "TELEGRAM_CHAT_IDS": "",
    }

    values = normalize_env(read_env_vars(ENV_FILE))
    for key, value in defaults.items():
        values.setdefault(key, value)

    if non_interactive:
        write_env_vars(ENV_FILE, values)
        ok("Normalized backend/.env defaults (non-interactive mode)")
        return

    if not prompt_yes_no("Run guided config now?", default=True):
        info("Skipping guided config. Edit backend/.env when ready.")
        return

    values["OPENAI_API_KEY"] = prompt_value("OPENAI_API_KEY", values["OPENAI_API_KEY"], secret=True)
    values["OPENROUTER_API_KEY"] = prompt_value("OPENROUTER_API_KEY", values["OPENROUTER_API_KEY"], secret=True)
    values["ANTHROPIC_API_KEY"] = prompt_value("ANTHROPIC_API_KEY", values["ANTHROPIC_API_KEY"], secret=True)
    values["GOOGLE_API_KEY"] = prompt_value("GOOGLE_API_KEY", values["GOOGLE_API_KEY"], secret=True)
    values["GEMINI_API_KEY"] = prompt_value("GEMINI_API_KEY", values["GEMINI_API_KEY"], secret=True)

    values["OLLAMA_BASE_URL"] = prompt_value("OLLAMA_BASE_URL", values["OLLAMA_BASE_URL"])
    values["COMFYUI_URL"] = prompt_value("COMFYUI_URL", values["COMFYUI_URL"])

    if values["MODELMESH_API_KEY"] == "modelmesh_local_dev_key":
        if prompt_yes_no("Use a custom MODELMESH_API_KEY now?", default=False):
            values["MODELMESH_API_KEY"] = prompt_value(
                "MODELMESH_API_KEY",
                values["MODELMESH_API_KEY"],
                secret=True,
            )

    write_env_vars(ENV_FILE, values)
    ok("Saved backend/.env")

    cloud_keys_present = any(
        values.get(key)
        for key in [
            "OPENAI_API_KEY",
            "OPENROUTER_API_KEY",
            "ANTHROPIC_API_KEY",
            "GOOGLE_API_KEY",
            "GEMINI_API_KEY",
        ]
    )
    if cloud_keys_present:
        ok("At least one cloud provider key is configured")
    else:
        warn("No cloud provider keys configured")

    if check_ollama(values["OLLAMA_BASE_URL"]):
        ok("Ollama endpoint is reachable")
    else:
        warn("Ollama not reachable right now (fine if you plan to use cloud providers)")


def create_start_scripts():
    header("Creating Start Scripts")

    if IS_WIN:
        bat = ROOT / "start.bat"
        bat.write_text(
            "@echo off\n"
            "setlocal\n\n"
            "cd /d \"%~dp0\"\n"
            "echo Starting DevForgeAI (hardened startup)...\n"
            "echo.\n"
            "python devforgeai.py start\n\n"
            "if errorlevel 1 (\n"
            "  echo.\n"
            "  echo Startup failed. See output above for health check details.\n"
            "  pause\n"
            ")\n",
            encoding="utf-8",
        )
        ok("Created start.bat")
    else:
        sh = ROOT / "start.sh"
        sh.write_text(
            "#!/usr/bin/env bash\n"
            "set -e\n"
            f"cd \"{ROOT}\"\n\n"
            "echo \"Starting DevForgeAI (hardened startup)...\"\n"
            "python3 devforgeai.py start\n",
            encoding="utf-8",
        )
        sh.chmod(0o755)
        ok("Created start.sh")


def print_summary():
    header("Installation Complete")
    print(
        f"""
  {GREEN}{BOLD}DevForgeAI is ready.{RESET}

  {BOLD}Recommended commands:{RESET}

    First-time setup:
      {CYAN}python devforgeai.py bootstrap{RESET}

    After every git pull:
      {CYAN}python devforgeai.py sync{RESET}

    Start app:
      {CYAN}python devforgeai.py start{RESET}

  {BOLD}URLs:{RESET}
    Frontend  ->  http://localhost:3001
    Backend   ->  http://localhost:19001
    API Docs  ->  http://localhost:19001/docs
"""
    )


def main():
    args = parse_args()

    print(
        f"""
{BOLD}{CYAN}
  DevForgeAI
  ----------
  AI Development Platform
{RESET}
  {BOLD}Installer -- {OS}{RESET}
"""
    )

    check_python()
    check_node()
    install_backend()
    install_frontend()
    setup_env()

    if args.configure:
        configure_env_walkthrough(non_interactive=False)
    elif args.non_interactive:
        configure_env_walkthrough(non_interactive=True)
    elif not args.no_config and sys.stdin.isatty():
        configure_env_walkthrough(non_interactive=False)

    create_start_scripts()
    print_summary()


if __name__ == "__main__":
    main()
