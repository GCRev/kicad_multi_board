"""KiCad action: export every tagged board from the open panel."""
import sys

from multiboard.ipc import run_action

if __name__ == "__main__":
    sys.exit(run_action(dry_run=False))
