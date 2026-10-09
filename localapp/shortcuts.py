"""Start-menu and sign-in (Startup folder) shortcuts. No admin rights needed."""
import os
import subprocess
from pathlib import Path

from localapp import config

START_MENU_LINK = lambda: config.programs_folder() / f"{config.APP_NAME}.lnk"
STARTUP_LINK = lambda: config.startup_folder() / f"{config.APP_NAME}.lnk"

# Paths go through environment variables, so nothing needs quoting in the script.
_CREATE_LINK = r"""
$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK_PATH)
$s.TargetPath = $env:LNK_TARGET
$s.Arguments = $env:LNK_ARGS
$s.WorkingDirectory = $env:LNK_DIR
$s.IconLocation = $env:LNK_ICON
$s.Description = $env:LNK_DESC
$s.Save()
"""


def _create_link(path: Path, arguments: str, description: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "LNK_PATH": str(path), "LNK_TARGET": str(config.PYTHONW), "LNK_ARGS": arguments,
           "LNK_DIR": str(config.ROOT), "LNK_ICON": f"{config.ICON},0", "LNK_DESC": description}
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _CREATE_LINK],
                   env=env, check=True, capture_output=True, creationflags=0x08000000)


def install_start_menu() -> Path:
    from localapp.icon import write_icon
    write_icon(config.ICON)
    link = START_MENU_LINK()
    _create_link(link, "-m localapp launch", f"Open {config.APP_NAME} (starts it if needed)")
    return link


def autostart_enabled() -> bool:
    return STARTUP_LINK().exists()


def set_autostart(enabled: bool) -> None:
    """On: start quietly in the background when you sign in to Windows."""
    if enabled:
        _create_link(STARTUP_LINK(), "-m localapp launch --background", f"Start {config.APP_NAME} in the background")
    else:
        STARTUP_LINK().unlink(missing_ok=True)


def uninstall() -> None:
    START_MENU_LINK().unlink(missing_ok=True)
    STARTUP_LINK().unlink(missing_ok=True)
