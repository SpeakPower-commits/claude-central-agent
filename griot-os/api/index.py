"""Vercel serverless entrypoint.

Vercel executes this file directly, so the project root is not guaranteed to be
on sys.path and `from app.main import app` fails with ImportError. Prepending
the parent directory makes the `app` package importable in both the Vercel
runtime and a plain `python api/index.py`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402  (import must follow the path fix)

__all__ = ["app"]
