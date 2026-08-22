#!/usr/bin/env python3
"""Preview or apply a conservative mechanical rename of an Hrz3 fork."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_OLD_PACKAGE = "agent_registry"
_OLD_CLI = "agent-registry"
_OLD_ENV_PREFIX = "HRZ_REGISTRY_"
_OLD_RESOURCE = "agent-registry"
_OLD_DIST = "agent-registry"
_SKIP_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".terraform",
    "build",
    "dist",
}
_TEXT_SUFFIXES = {
    "",
    ".env",
    ".example",
    ".html",
    ".ini",
    ".json",
    ".lock",
    ".md",
    ".py",
    ".tf",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
_TOOL_FILES = {Path("scripts/rename_fork.py"), Path("tests/test_rename_fork.py")}


def _iter_files(include_docs: bool) -> list[Path]:
    files = []
    for path in _ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(_ROOT)
        if relative in _TOOL_FILES or any(part in _SKIP_DIRS for part in relative.parts):
            continue
        if path.suffix not in _TEXT_SUFFIXES:
            continue
        if not include_docs and path.suffix in {".md", ".html"}:
            continue
        files.append(path)
    return files


def _replacements(args: argparse.Namespace) -> list[tuple[str, str]]:
    prefix = args.env_prefix.rstrip("_").upper() + "_"
    # The distribution name is the same token as the resource name, so replacing it bare
    # consumes every occurrence and leaves the entries below doing nothing: a --dist that
    # differs from --resource would silently rewrite the resource name too. Anchoring the
    # distribution on its pyproject declaration keeps the two independently meaningful.
    return [
        (f'name = "{_OLD_DIST}"', f'name = "{args.dist or args.resource}"'),
        (
            f'{_OLD_CLI} = "{_OLD_PACKAGE}.cli.main:main"',
            f'{args.cli} = "{args.package}.cli.main:main"',
        ),
        (_OLD_RESOURCE, args.resource),
        (_OLD_PACKAGE, args.package),
        (_OLD_CLI, args.cli),
        (_OLD_ENV_PREFIX, prefix),
    ]


def _rewrite_text(text: str, replacements: list[tuple[str, str]]) -> tuple[str, int]:
    count = 0
    for old, new in replacements:
        if old == _OLD_ENV_PREFIX:
            text, changed = re.subn(rf"\b{re.escape(old)}(?=[A-Z0-9])", new, text)
        else:
            changed = text.count(old)
            text = text.replace(old, new)
        count += changed
    return text, count


def _preflight_package_rename(new_package: str) -> tuple[Path, Path]:
    source = _ROOT / "src" / _OLD_PACKAGE
    destination = _ROOT / "src" / new_package
    if source != destination and destination.exists():
        raise RuntimeError(f"refusing rename: destination package already exists: {destination}")
    if not source.exists():
        raise RuntimeError(f"refusing rename: source package does not exist: {source}")
    return source, destination


def main() -> int:
    parser = argparse.ArgumentParser(description="Rename an Hrz3 institutional fork.")
    parser.add_argument("--package", required=True)
    parser.add_argument("--cli", required=True)
    parser.add_argument("--env-prefix", required=True)
    parser.add_argument("--resource", required=True)
    parser.add_argument("--dist", default="")
    parser.add_argument("--include-docs", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()

    if not re.fullmatch(r"[a-z_][a-z0-9_]*", args.package):
        parser.error("--package must be a valid snake_case identifier")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", args.cli):
        parser.error("--cli must be a lowercase kebab-case command")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", args.resource):
        parser.error("--resource must be a lowercase kebab-case stem")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", args.env_prefix.rstrip("_")):
        parser.error("--env-prefix must contain only letters, digits and underscores")
    if args.dist and not re.fullmatch(
        r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?",
        args.dist,
    ):
        parser.error("--dist must be a valid Python distribution name")
    if args.cli != args.resource:
        parser.error(
            "--cli and --resource must match because the upstream name "
            "'agent-registry' is shared by both surfaces"
        )

    source, destination = _preflight_package_rename(args.package)
    apply_changes = args.yes and not args.dry_run
    replacements = _replacements(args)
    print("Planned replacements:")
    for old, new in replacements:
        print(f"  {old!r} -> {new!r}")

    touched: list[tuple[Path, int]] = []
    for path in _iter_files(args.include_docs):
        try:
            original = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rewritten, count = _rewrite_text(original, replacements)
        if count:
            touched.append((path, count))
            if apply_changes:
                path.write_text(rewritten, encoding="utf-8")

    print(
        f"{'Edited' if apply_changes else 'Would edit'} {len(touched)} file(s), "
        f"{sum(count for _, count in touched)} replacement(s)."
    )
    if source != destination:
        print(f"{'Renaming' if apply_changes else 'Would rename'} {source} -> {destination}")
        if apply_changes:
            source.rename(destination)
    if not apply_changes:
        print("No files were written. Re-run with --yes after reviewing the preview.")
    else:
        print("Rename complete. Recreate the environment and run the full adoption gate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
