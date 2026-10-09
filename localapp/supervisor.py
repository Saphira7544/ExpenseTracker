"""Keeps the web server running in the background.

The app runs in a child process. When it exits with RESTART_EXIT_CODE (the
Restart button), the supervisor starts it again, so code changes are picked
up; if requirements.txt changed, dependencies are installed first. If the
child crashes it is restarted with a back-off; repeated crashes stop it.
"""
import ctypes
import datetime as dt
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

from localapp import config

CREATE_NO_WINDOW = 0x08000000


def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    code = ctypes.c_ulong()
    kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
    kernel32.CloseHandle(handle)
    return code.value == 259                             # STILL_ACTIVE


def ping(port: int, timeout: float = 1.5) -> bool:
    """True if *our* app answers on this port (something else may own port 80 later)."""
    try:
        with urllib.request.urlopen(f"http://{config.HOST}:{port}/api/system/ping", timeout=timeout) as r:
            return json.loads(r.read()).get("app") == "expense-tracker"
    except Exception:
        return False


def port_free(port: int) -> bool:
    with socket.socket() as s:
        try:
            s.bind((config.HOST, port))
            return True
        except OSError:
            return False


def log(message: str) -> None:
    config.RUNTIME_DIR.mkdir(exist_ok=True)
    with open(config.LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] supervisor: {message}\n")


def rotate_log() -> None:
    if config.LOG_FILE.exists() and config.LOG_FILE.stat().st_size > 5 * 1024 * 1024:
        config.LOG_FILE.replace(config.LOG_FILE.with_suffix(".log.1"))


def install_requirements_if_changed() -> None:
    req = config.ROOT / "requirements.txt"
    digest = hashlib.sha256(req.read_bytes()).hexdigest()
    previous = config.REQUIREMENTS_HASH.read_text().strip() if config.REQUIREMENTS_HASH.exists() else None
    if digest == previous:
        return
    if previous is not None:   # first run: assume the venv is already set up
        log("requirements.txt changed: installing dependencies")
        with open(config.LOG_FILE, "a", encoding="utf-8") as out:
            result = subprocess.run([str(config.PYTHON), "-m", "pip", "install", "-r", str(req)],
                                    cwd=config.ROOT, stdout=out, stderr=subprocess.STDOUT,
                                    creationflags=CREATE_NO_WINDOW)
        if result.returncode != 0:
            log("pip install failed; starting with the current packages (see above)")
            return
    config.REQUIREMENTS_HASH.write_text(digest)


def serve() -> None:
    runtime = config.read_runtime()
    if runtime and pid_alive(runtime.get("supervisor_pid")) and ping(runtime.get("port", 0)):
        return   # already running

    port = next((p for p in config.PORTS if port_free(p)), None)
    if port is None:
        log(f"no free port among {config.PORTS}; not starting")
        return
    config.STOP_FLAG.unlink(missing_ok=True)
    config.write_runtime({"supervisor_pid": os.getpid(), "port": port, "url": config.url_for(port),
                          "started_at": dt.datetime.now().isoformat(timespec="seconds")})

    env = {**os.environ,
           config.MANAGED_ENV: "1",
           "EXPENSE_TRACKER_URL": config.url_for(port),
           "COOKIE_SECURE": "false",          # plain http on this PC only
           "PYTHONIOENCODING": "utf-8",
           "PYTHONUNBUFFERED": "1"}
    crashes = []
    try:
        while True:
            rotate_log()
            install_requirements_if_changed()
            log(f"starting server on {config.url_for(port)}")
            with open(config.LOG_FILE, "a", encoding="utf-8") as out:
                child = subprocess.Popen(
                    [str(config.PYTHONW), "-m", "uvicorn", "app.main:app", "--host", config.HOST, "--port", str(port)],
                    cwd=config.ROOT, env=env, stdout=out, stderr=subprocess.STDOUT, creationflags=CREATE_NO_WINDOW,
                )
                code = child.wait()

            if code == config.RESTART_EXIT_CODE:
                log("restart requested")
                continue
            if config.STOP_FLAG.exists():
                log("stop requested")
                break
            now = time.time()
            crashes = [t for t in crashes if now - t < 120] + [now]
            if len(crashes) >= 5:
                log(f"server exited with code {code} five times in two minutes; giving up")
                break
            log(f"server exited with code {code}; restarting in {5 * len(crashes)}s")
            time.sleep(5 * len(crashes))
    finally:
        config.STOP_FLAG.unlink(missing_ok=True)
        if (config.read_runtime() or {}).get("supervisor_pid") == os.getpid():
            config.RUNTIME_FILE.unlink(missing_ok=True)
