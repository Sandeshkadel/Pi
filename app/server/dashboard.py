"""Load the packaged mobile-friendly status dashboard."""

from importlib.resources import files

DASHBOARD_HTML = files("dashboard").joinpath("index.html").read_text(encoding="utf-8")
