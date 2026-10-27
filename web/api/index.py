"""Vercel entry point: serves the Noether API (noether/server.py) at /api/*.

The noether package is copied to web/py/noether by `npm run sync:noether`, because a function
rooted at web/ cannot import from the repository root. In a full checkout the root works too.
"""
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
for candidate in (here.parent / "py", here.parent.parent):
    if (candidate / "noether" / "server.py").is_file():
        sys.path.insert(0, str(candidate))
        break

from noether.server import app  # noqa: E402,F401
