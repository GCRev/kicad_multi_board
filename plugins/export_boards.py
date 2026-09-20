"""KiCad action: open the multi-board export window."""
import sys

from multiboard.ipc import run_ui

if __name__ == "__main__":
    sys.exit(run_ui())
