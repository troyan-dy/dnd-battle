"""Architectural guard tests for the isolated rules engine (CLAUDE.md rule 4).

The D&D 2024 rules math must stay PURE — importing only the standard library and
its sibling rules modules, never the transport / API / persistence / service /
schema / storage / security layers (nor their frameworks). Outer layers depend on
``app.rules``; the rules engine never depends back. These tests enforce that
boundary mechanically by parsing every module under ``app/rules`` with ``ast`` so
a future rules task that accidentally reaches outward fails CI immediately.

They also pin the package's public API surface (``app.rules.__all__``), the
supported contract that later Phase-6 tasks extend.
"""

from __future__ import annotations

import ast
import pkgutil
from collections.abc import Iterator
from pathlib import Path

from app import rules

# Layers the pure rules engine must never import (outer app packages) plus the
# frameworks that only belong in those outer layers.
_FORBIDDEN_PREFIXES = (
    "app.api",
    "app.realtime",
    "app.db",
    "app.models",
    "app.services",
    "app.schemas",
    "app.storage",
    "app.security",
    "app.main",
    "app.config",
    "fastapi",
    "starlette",
    "socketio",
    "sqlalchemy",
    "alembic",
    "pydantic",
    "httpx",
)

_RULES_DIR = Path(rules.__file__).parent


def _rules_module_files() -> list[Path]:
    files = sorted(_RULES_DIR.glob("*.py"))
    assert files, "expected at least one module under app/rules"
    return files


def _imported_names(source: str) -> Iterator[str]:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module


def test_rules_modules_import_only_pure_layers() -> None:
    offenders: dict[str, list[str]] = {}
    for path in _rules_module_files():
        bad = [
            name
            for name in _imported_names(path.read_text(encoding="utf-8"))
            if name.startswith(_FORBIDDEN_PREFIXES)
        ]
        if bad:
            offenders[path.name] = bad
    assert not offenders, f"rules engine reached outside its boundary: {offenders!r}"


def test_rules_package_only_contains_rules_modules() -> None:
    # No accidental sub-packages dragging in heavier dependencies.
    modules = pkgutil.iter_modules([str(_RULES_DIR)])
    discovered = sorted(module.name for module in modules)
    assert discovered == ["abilities", "attack", "conditions", "damage", "dice"], discovered


def test_public_api_surface_is_importable_from_package() -> None:
    # The supported contract: consumers import from `app.rules`, not submodules.
    for name in rules.__all__:
        assert hasattr(rules, name), f"app.rules.__all__ promises missing {name!r}"


def test_public_api_matches_dice_reexports() -> None:
    dice = rules.dice

    assert rules.parse_dice is dice.parse_dice
    assert rules.roll_dice is dice.roll_dice
    assert rules.D20_SIDES == dice.D20_SIDES
