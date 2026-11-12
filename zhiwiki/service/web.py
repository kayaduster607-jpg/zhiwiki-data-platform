"""Same-origin workbench assets; no user paths or external scripts are served."""

from pathlib import Path

from .common import ServiceError


ROOT = Path(__file__).parent / "console"
ASSETS = frozenset({"style.css", "app.js", "api.js", "ui.js", "sources.js", "tasks.js",
                    "review.js", "evidence.js", "access.js", "operations.js"})
CONSOLE = (ROOT / "index.html").read_text(encoding="utf-8")


def public_asset(path):
    return path.startswith("/assets/team/") and path[len("/assets/team/"):] in ASSETS


def asset_path(name):
    if name not in ASSETS:
        raise ServiceError(404, "RESOURCE_NOT_FOUND")
    return ROOT / name
