"""Launcher for the Streamlit dashboard."""

from pathlib import Path
import sys
from streamlit.web import cli as stcli


def run_dashboard() -> None:
    """Launch the read-only Streamlit dashboard."""
    app_path = str(Path(__file__).parent / "app.py")
    sys.argv = [
        "streamlit",
        "run",
        app_path,
        "--browser.gatherUsageStats=false",
    ]
    sys.exit(stcli.main())
