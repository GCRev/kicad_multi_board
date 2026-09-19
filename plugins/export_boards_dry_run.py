"""KiCad action: report what an export would produce, without writing any output."""
import sys

from multiboard.ipc import run_action

if __name__ == "__main__":
    sys.exit(run_action(dry_run=True))
