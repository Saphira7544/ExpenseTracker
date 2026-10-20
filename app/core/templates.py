import os
from fastapi.templating import Jinja2Templates

STATIC_DIR = "app/static"


def static_url(path: str) -> str:
    """URL of a static file with its modification time appended.

    The server sends no cache headers, so browsers guess how long to keep
    CSS/JS and can mix a stale cached script with a newer page. A changed
    file gets a new URL, so the browser always fetches it fresh.
    """
    try:
        version = int(os.path.getmtime(os.path.join(STATIC_DIR, path)))
    except OSError:
        version = 0
    return f"/static/{path}?v={version}"


# Shared by every router that renders pages, so they all get static_url().
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["static_url"] = static_url
# Built-in colours plus the user's own categories' (base.html: category_colors(user)).
def _category_colors(user: dict | None) -> dict:
    from app.services.categories import colors_for  # imported late: it needs the database engine
    return colors_for(user["id"] if user else None)


templates.env.globals["category_colors"] = _category_colors
