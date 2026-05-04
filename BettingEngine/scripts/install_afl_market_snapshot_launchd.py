#!/usr/bin/env python3
from __future__ import annotations

import argparse
import plistlib
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
LABEL = "com.bettingmodel.afl-market-snapshot"


def main() -> None:
    parser = argparse.ArgumentParser(description="Install macOS launchd schedule for daily AFL market snapshots.")
    parser.add_argument("--config", default="config/betmate_automation.yaml")
    parser.add_argument("--hour", type=int, default=9)
    parser.add_argument("--minute", type=int, default=5)
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--load", action="store_true")
    args = parser.parse_args()

    agents_dir = Path.home() / "Library" / "LaunchAgents"
    plist_path = agents_dir / f"{LABEL}.plist"

    if args.uninstall:
        unload(plist_path)
        if plist_path.exists():
            plist_path.unlink()
            print(f"Removed {plist_path}")
        return

    agents_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = ROOT / "logs" / "market_snapshots"
    logs_dir.mkdir(parents=True, exist_ok=True)

    program_args = [
        sys.executable,
        str(ROOT / "scripts" / "afl_market_snapshot.py"),
        "--config",
        args.config,
        "--days",
        "10",
    ]

    plist = {
        "Label": LABEL,
        "ProgramArguments": program_args,
        "WorkingDirectory": str(ROOT),
        "StartCalendarInterval": {"Hour": args.hour, "Minute": args.minute},
        "StandardOutPath": str(logs_dir / "afl_launchd.out.log"),
        "StandardErrorPath": str(logs_dir / "afl_launchd.err.log"),
        "RunAtLoad": False,
        "EnvironmentVariables": {
            "PATH": f"{ROOT / '.venv' / 'bin'}:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        },
    }

    with plist_path.open("wb") as fh:
        plistlib.dump(plist, fh)

    print(f"Wrote {plist_path}")
    print(f"Schedule: daily {args.hour:02d}:{args.minute:02d}")
    print(f"Command: {' '.join(program_args)}")

    if args.load:
        unload(plist_path)
        subprocess.run(["launchctl", "load", str(plist_path)], check=True)
        print("LaunchAgent loaded.")
    else:
        print(f"To load it: launchctl load {plist_path}")


def unload(plist_path: Path) -> None:
    if plist_path.exists():
        subprocess.run(["launchctl", "unload", str(plist_path)], check=False)


if __name__ == "__main__":
    main()
