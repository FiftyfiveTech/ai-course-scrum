"""
Read KEY=VALUE env files so `make doctor` sees the same settings you wrote down.

Precedence, first non-empty value wins:
    1. the process environment
    2. ./.env                              (written by `make setup`, gitignored)
    3. ~/.config/ai-course-scrum/.env      (where secrets live, per CLAUDE.md)

An empty value never wins: the .env that `make setup` copies from .env.example has every
key blank, and it must not hide the real ones in ~/.config/.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

CONFIG_ENV = Path.home() / ".config" / "ai-course-scrum" / ".env"
LOCAL_ENV = Path(".env")


def parse(text: str) -> dict[str, str]:
    """`KEY=VALUE` lines. Blank lines, `#` comments and a leading `export ` are allowed.
    A value may be quoted; an unquoted value ends at ` #`."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        line = line.removeprefix("export ").lstrip()
        key, sep, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not sep or not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].rstrip()
        out[key] = value
    return out


def load(
    environ: Mapping[str, str] = os.environ,
    files: tuple[Path, ...] | None = None,
) -> tuple[dict[str, str], list[Path]]:
    """Merged env and the files that were actually read, highest precedence first."""
    layers: list[Mapping[str, str]] = [environ]
    read: list[Path] = []
    for path in files if files is not None else (LOCAL_ENV, CONFIG_ENV):
        if path.is_file():
            layers.append(parse(path.read_text(encoding="utf-8")))
            read.append(path)
    merged: dict[str, str] = {}
    for layer in reversed(layers):
        merged.update({k: v for k, v in layer.items() if v.strip()})
    return merged, read
