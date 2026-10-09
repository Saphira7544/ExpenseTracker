import json
import os
from pathlib import Path

APP_NAME = "Expense Tracker"
ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / ".venv" / "Scripts"
PYTHON = SCRIPTS / "python.exe"
PYTHONW = SCRIPTS / "pythonw.exe"      # no console window
ICON = Path(__file__).resolve().parent / "expense-tracker.ico"

HOST = "127.0.0.1"                     # this PC only, never the network
HOSTNAME = "expenses.localhost"        # browsers resolve *.localhost to this PC
PORTS = [80, 8500]                     # 80 gives a URL without a port; 8500 if 80 is taken

RUNTIME_DIR = ROOT / "logs"
RUNTIME_FILE = RUNTIME_DIR / "runtime.json"
LOG_FILE = RUNTIME_DIR / "server.log"
STOP_FLAG = RUNTIME_DIR / "stop.flag"
REQUIREMENTS_HASH = RUNTIME_DIR / "requirements.sha256"

RESTART_EXIT_CODE = 3                  # the app exits with this to ask the supervisor for a restart
MANAGED_ENV = "EXPENSE_TRACKER_LOCAL"  # set for the app when it runs under the supervisor


def url_for(port: int) -> str:
    return f"http://{HOSTNAME}" + ("" if port == 80 else f":{port}")


def read_runtime() -> dict | None:
    try:
        return json.loads(RUNTIME_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_runtime(data: dict) -> None:
    RUNTIME_DIR.mkdir(exist_ok=True)
    RUNTIME_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def startup_folder() -> Path:
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def programs_folder() -> Path:
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
