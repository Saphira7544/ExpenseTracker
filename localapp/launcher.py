import ctypes
import os
import subprocess
import time
import webbrowser

from localapp import config
from localapp.supervisor import pid_alive, ping

DETACHED = 0x00000008 | 0x00000200 | 0x08000000   # DETACHED_PROCESS | NEW_PROCESS_GROUP | NO_WINDOW
START_TIMEOUT_SECONDS = 90                          # first start may install packages


def running_url() -> str | None:
    rt = config.read_runtime()
    if rt and pid_alive(rt.get("supervisor_pid")) and ping(rt.get("port", 0)):
        return rt["url"]
    return None


def start_supervisor() -> None:
    subprocess.Popen([str(config.PYTHONW), "-m", "localapp", "serve"], cwd=config.ROOT,
                     creationflags=DETACHED, close_fds=True)


def launch(open_browser: bool = True) -> None:
    url = running_url()
    if url is None:
        rt = config.read_runtime()
        if not (rt and pid_alive(rt.get("supervisor_pid"))):   # not already starting up
            start_supervisor()
        deadline = time.time() + START_TIMEOUT_SECONDS
        while url is None and time.time() < deadline:
            time.sleep(0.5)
            url = running_url()
    if url is None:
        ctypes.windll.user32.MessageBoxW(
            None, f"{config.APP_NAME} didn't start.\n\nDetails are in:\n{config.LOG_FILE}",
            config.APP_NAME, 0x10)
        if config.LOG_FILE.exists():
            os.startfile(config.LOG_FILE)
        return
    if open_browser:
        webbrowser.open(url)
