"""Keeps every Markdown table row inside the repo's 100-character budget.

AGENTS.md (Formatting) requires tables to read aligned in plaintext: prettier
pads each column to its widest cell, so one long cell stretches every row in the
table. The rule caps the whole padded row at 100 characters and lists the ways
out — tighten cells, factor a shared path prefix into a note above the table,
drop or merge columns, or move detail into a terse `Details:` list underneath.
Content that cannot fit becomes a bulleted list instead.

Prettier cannot enforce this: `--print-width` governs prose, and tables are
always padded to their content. markdownlint's MD013 is the nearest off-the-
shelf rule, but its `line_length` applies to paragraphs as well as tables, so
turning it on at 100 would flag the long prose lines this repo keeps
deliberately (`--prose-wrap=preserve`). Hence this check.

Width is counted in characters, not bytes. An em dash costs three bytes in
UTF-8, so a byte-based count (`awk`, `wc -c`) reports rows as over-long when
they are not.
"""

from pathlib import Path

from shared.paths import REPO_ROOT

LIMIT = 100

# Not repo-authored documentation: vendored, generated, or reference-only trees.
# `resources/` is reference material the mod must not modify (AGENTS.md).
_SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "dist",
    ".astro",
    "resources",
}

# The published docs site renders to HTML, where plaintext column alignment
# buys nothing, and its tables are data (every country, every author) that no
# amount of tightening fits in 100 characters. Dev diaries are additionally
# reproduced verbatim from their author's original. markdownlint-cli2 already
# lints this tree with MD013 switched off (docs/.markdownlint-cli2.jsonc).
_SKIP_PREFIXES = ("docs/src/content/",)

# Deliberate exemptions, as repo-relative paths. Add an entry only for a table
# that genuinely cannot be reshaped, and say why — never to silence a real
# offender.
_ALLOWLIST: dict[str, str] = {}


def _iter_markdown() -> list[Path]:
    out: list[Path] = []
    for path in sorted(REPO_ROOT.rglob("*")):
        if path.suffix not in (".md", ".mdx") or not path.is_file():
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        out.append(path)
    return out


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _table_rows(text: str):
    """Yield (line number, line) for table rows, skipping fenced code blocks."""
    fence = ""
    for number, line in enumerate(text.split("\n"), start=1):
        stripped = line.lstrip()
        if fence:
            if stripped.startswith(fence):
                fence = ""
            continue
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fence = stripped[:3]
            continue
        if stripped.startswith("|"):
            yield number, line


def _offenders(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    return [
        f"{_rel(path)}:{number} is {len(line)} chars"
        for number, line in _table_rows(text)
        if len(line) > LIMIT
    ]


def test_markdown_table_rows_fit_the_width_budget():
    failures: list[str] = []
    for path in _iter_markdown():
        rel = _rel(path)
        if rel in _ALLOWLIST or rel.startswith(_SKIP_PREFIXES):
            continue
        failures.extend(_offenders(path))
    assert not failures, "Markdown table rows over {} characters:\n  {}".format(
        LIMIT, "\n  ".join(failures)
    )


def test_allowlist_entries_still_exist_and_still_need_the_exemption():
    """A stale entry silently exempts whatever later takes that path."""
    live = {_rel(p) for p in _iter_markdown()}
    missing = sorted(set(_ALLOWLIST) - live)
    assert not missing, f"Allowlist entries no longer exist: {missing}"
    unneeded = sorted(rel for rel in _ALLOWLIST if not _offenders(REPO_ROOT / rel))
    assert not unneeded, f"Allowlist entries no longer needed: {unneeded}"
