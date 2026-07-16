import importlib.util
import os
import sys
from pathlib import Path


def _use_existing_langgraph_runtime() -> None:
    if importlib.util.find_spec("langgraph") is not None:
        return
    existing_python = Path.home() / "ENTER" / "bin" / "python3"
    if existing_python.is_file() and Path(sys.executable).resolve() != existing_python.resolve():
        os.execv(str(existing_python), [str(existing_python), str(Path(__file__).resolve()), *sys.argv[1:]])
    raise RuntimeError(
        "LangGraph is not importable and the verified existing ~/ENTER/bin/python3 runtime is unavailable. "
        "No dependency was installed."
    )


_use_existing_langgraph_runtime()

from evalreliability.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
