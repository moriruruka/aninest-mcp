"""Puts ``src`` on sys.path so the tests run without an editable install.

Also forces UTF-8 on stdout/stderr: several tests and the evaluation script print
non-ASCII text, and the default console encoding on Windows runners (cp1252) would
raise ``UnicodeEncodeError`` there.
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _force_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):  # pragma: no cover - unusual streams
                pass


_force_utf8()
