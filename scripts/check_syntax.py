"""Available even offline; complements Ruff and does not replace it."""
import ast
from pathlib import Path

paths = [*Path("services").rglob("*.py"), *Path("tests").rglob("*.py")]
for path in paths:
    ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
print(f"Parsed {len(paths)} Python source files")
