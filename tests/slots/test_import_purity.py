"""Guard tests for the pure-engine boundary (S1 spec §Allowed imports).

The slot generation engine must stay free of I/O and framework dependencies:
no SQLAlchemy, no FastAPI, no app.core, no ORM models, no repositories, and no
clock access (datetime.now / utcnow / date.today).
"""

import ast
from pathlib import Path

MODULE_PATH = Path("app/slots/slot_generation.py")

ALLOWED_APP_MODULES = {"app.availability.enums", "app.event_types.enums"}

FORBIDDEN_PREFIXES = ("sqlalchemy", "fastapi", "app.core")
FORBIDDEN_SUBSTRINGS = (".model", ".repository", ".service", ".router", ".schema", ".config")


def _imported_modules(tree: ast.AST) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def test_no_forbidden_imports() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for module in _imported_modules(tree):
        assert not module.startswith(FORBIDDEN_PREFIXES), (
            f"pure engine imports forbidden module: {module}"
        )
        assert not any(sub in module for sub in FORBIDDEN_SUBSTRINGS), (
            f"pure engine imports ORM/framework module: {module}"
        )
        if module.startswith("app"):
            assert module in ALLOWED_APP_MODULES, (
                f"pure engine imports unexpected app module: {module}"
            )


def test_no_clock_access() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr in ("now", "utcnow", "today")
            and isinstance(func.value, ast.Name)
            and func.value.id in ("datetime", "date")
        ):
            raise AssertionError(f"pure engine accesses the clock: {func.attr}")
