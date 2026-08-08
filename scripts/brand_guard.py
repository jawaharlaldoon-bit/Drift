"""Fail when legacy product or deployment identity leaks outside the compliance folder."""

from __future__ import annotations

import sys
from pathlib import Path

LEGACY_TERMS = (
    "cas" + "sandra",
    "ari" + "ze",
    "phoe" + "nix",
    "shop" + "bot",
    "elianna-" + "unpolymerized-confidingly",
    "905" + "502723393",
    "1519" + "338702365523968",
)
SKIP_DIRS = {".git", ".venv", "node_modules", "dist", "__pycache__", ".pytest_cache"}
TEXT_SUFFIXES = {
    ".py", ".md", ".toml", ".json", ".yaml", ".yml", ".html", ".css", ".tsx",
    ".ts", ".js", ".svg", ".txt", ".example", ".ps1", ".dockerignore", ".gitignore",
}


def scan(root: Path) -> list[str]:
    violations: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or "licence" in path.parts or any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"LICENSE", "Dockerfile"}:
            continue
        try:
            text = path.read_text(encoding="utf-8").lower()
        except UnicodeDecodeError:
            continue
        for term in LEGACY_TERMS:
            if term in text:
                violations.append(f"{path.relative_to(root)} contains blocked legacy identity")
    return violations


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    violations = scan(root)
    if violations:
        print("\n".join(violations), file=sys.stderr)
        raise SystemExit(1)
    print("Drift brand guard passed.")


if __name__ == "__main__":
    main()
