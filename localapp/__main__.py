import sys

from localapp import config, shortcuts


def main(argv: list[str]) -> None:
    command = argv[0] if argv else "launch"
    if command == "serve":
        from localapp.supervisor import serve
        serve()
    elif command == "launch":
        from localapp.launcher import launch
        launch(open_browser="--background" not in argv)
    elif command == "install":
        link = shortcuts.install_start_menu()
        print(f"Start-menu shortcut: {link}")
        print(f"Open it from Start > {config.APP_NAME}; the app runs at {config.url_for(config.PORTS[0])}")
    elif command == "uninstall":
        shortcuts.uninstall()
        print("Removed the Start-menu and startup shortcuts.")
    elif command == "autostart":
        if len(argv) > 1 and argv[1] in ("on", "off"):
            shortcuts.set_autostart(argv[1] == "on")
        print("Start at sign-in:", "on" if shortcuts.autostart_enabled() else "off")
    else:
        print(__doc__ or "", "Commands: install, uninstall, launch, serve, autostart on|off|status")


if __name__ == "__main__":
    main(sys.argv[1:])
