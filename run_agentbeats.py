from __future__ import annotations

import subprocess
import sys


def main() -> int:
    core = subprocess.run([sys.executable, "run.py"], check=False)
    if core.returncode != 0:
        return core.returncode
    adapter = subprocess.run(
        [sys.executable, "-m", "agentbeats_adapter.offline"],
        check=False,
    )
    return adapter.returncode


if __name__ == "__main__":
    raise SystemExit(main())
