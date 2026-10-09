"""Controls for the local desktop setup (localapp/): status, restart, stop, start-at-sign-in.

Only active when the app runs under the local supervisor, and only for an admin
on this PC; elsewhere (e.g. a hosted deployment) these return 404.
"""
import datetime as dt
import os
import subprocess
import threading
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.core.dependencies import get_current_user

router = APIRouter()

ROOT = Path(__file__).resolve().parents[3]
STARTED_AT = time.time()
CODE_DIRS = ["app", "categorizers", "legacy_db", "models", "parsers", "utils", "localapp"]
RESTART_EXIT_CODE = 3


def managed() -> bool:
    return os.environ.get("EXPENSE_TRACKER_LOCAL") == "1"


def require_local_admin(request: Request, user: dict = Depends(get_current_user)) -> dict:
    if not managed():
        raise HTTPException(status_code=404, detail="Not running as the local app")
    if not user.get("is_admin") or (request.client and request.client.host not in ("127.0.0.1", "::1")):
        raise HTTPException(status_code=403, detail="Only the admin on this PC can control the app")
    return user


def code_changed_since_start() -> bool:
    """Python files only: templates and static files are picked up without a restart."""
    for name in CODE_DIRS:
        for path in (ROOT / name).rglob("*.py"):
            if path.stat().st_mtime > STARTED_AT:
                return True
    return (ROOT / "requirements.txt").stat().st_mtime > STARTED_AT


def git_version() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                             text=True, timeout=3, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return out.stdout.strip() or None
    except Exception:
        return None


def exit_soon(code: int) -> None:
    # Give the HTTP response time to reach the browser, then let the supervisor act on the exit code.
    threading.Timer(0.5, lambda: os._exit(code)).start()


@router.get("/api/system/ping")
def ping():
    """Unauthenticated, so the launcher can tell this app is up (and is ours)."""
    return {"app": "expense-tracker"}


@router.get("/api/system/status")
def status(request: Request, user: dict = Depends(get_current_user)):
    if not managed():
        return {"managed": False}
    from localapp import shortcuts
    return {
        "managed": True,
        "can_control": bool(user.get("is_admin")) and bool(request.client) and request.client.host in ("127.0.0.1", "::1"),
        "url": os.environ.get("EXPENSE_TRACKER_URL"),
        "started_at": dt.datetime.fromtimestamp(STARTED_AT).isoformat(timespec="seconds"),
        "version": git_version(),
        "code_changed": code_changed_since_start(),
        "autostart": shortcuts.autostart_enabled(),
    }


@router.post("/api/system/restart")
def restart(user: dict = Depends(require_local_admin)):
    exit_soon(RESTART_EXIT_CODE)
    return {"status": "restarting"}


@router.post("/api/system/stop")
def stop(user: dict = Depends(require_local_admin)):
    from localapp import config
    config.STOP_FLAG.touch()
    exit_soon(0)
    return {"status": "stopping"}


class AutostartUpdate(BaseModel):
    enabled: bool


@router.put("/api/system/autostart")
def set_autostart(payload: AutostartUpdate, user: dict = Depends(require_local_admin)):
    from localapp import shortcuts
    shortcuts.set_autostart(payload.enabled)
    return {"autostart": shortcuts.autostart_enabled()}
