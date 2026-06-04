#!/usr/bin/env python3
"""
country_commit_counts.py - Count git commits that touched each country's content.

Trawls the full history reachable from a revision (default ``main``, which already
includes every commit on branches that were merged into it) and, for each commit,
works out which country (or countries) its changed files belong to. A commit that
edits ten German files counts as 1 for GER; a commit that edits both German and
French files counts 1 for GER and 1 for FRA.

Country attribution uses two signals, mirroring how Millennium Dawn names files:

  1. TAG token (whole repo) - any path component that is *exactly* an uppercase
     country tag, e.g. ``common/characters/ENG.txt``, ``goals_ENG.txt``,
     ``gfx/flags/ENG_democratic.tga``, ``germany - GER/foo.dds``.

  2. Name / demonym dictionary (only the directories that name files by country
     rather than tag: national_focus, events, ideas) - built from the game's own
     data, e.g. ``05_germany.txt`` -> GER, ``events/Brazil.txt`` -> BRA,
     ``ideas/Brazilian.txt`` -> BRA (demonym = country name + suffix).

Output is CSV ``TAG, count, name, loc`` sorted by descending commit count:
  * ``count`` - commits that touched the country's content
  * ``name``  - displayed name at game start, resolved through the starting ruling
                ideology (it can change the name, e.g. RAJ is 'India' but 'Delhi
                Caliphate' under fascism)
  * ``loc``   - rough lines of code: summed line counts of all text files at rev
                attributed to the tag. A file shared by N tags counts for all N;
                untagged or binary files count for none.
Pass ``--no-names`` / ``--no-loc`` to drop those columns.

Usage:
    python3 tools/analysis/country_commit_counts.py
    python3 tools/analysis/country_commit_counts.py --rev origin/main -o counts.csv
    python3 tools/analysis/country_commit_counts.py --no-names
    python3 tools/analysis/country_commit_counts.py --report-unmatched
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

# Directories whose files are named by country *name* (not tag). Name/demonym
# matching is restricted to these to avoid false positives elsewhere; TAG-token
# matching still applies to the whole repo.
NAME_DIRS = (
    "common/national_focus/",
    "events/",
    "common/ideas/",
)

# Highest-priority overrides for stems where a substring match would pick the
# wrong country (word order differs from the canonical name). Matched as a prefix
# of the normalised, prefix-stripped stem; checked before everything else.
STEM_OVERRIDES = {
    "koreanorth": "NKO",
    "koreasouth": "KOR",
    "koreaunified": "KOR",
    "koreaconfederation": "KOR",
}

# Alternate country names/spellings the game data does not contain under these
# forms. Long and unambiguous, so they are safe to match as a substring anywhere
# in a name-dir filename (e.g. 'MD_Russia' -> SOV via 'russia', 'WTT_Britain').
NAME_ALIASES = {
    "britain": "ENG",
    "greatbritain": "ENG",
    "unitedstates": "USA",
    "unitedstatesofamerica": "USA",
    "soviet": "SOV",
    "sovietunion": "SOV",
    "ussr": "SOV",
    "myanmar": "BRM",
    "netherlands": "HOL",
}

# Short, ambiguous aliases matched only when they are the *entire* stem
# (substring matching 'uk' would wrongly hit 'ukraine').
EXACT_ALIASES = {
    "uk": "ENG",
    "usa": "USA",
}

# Demonyms whose country name is not a prefix of the demonym (French != France*),
# so the dictionary cannot derive them. Matched as a prefix of the stem, e.g.
# 'German.txt' / 'American DJT.txt'. Includes a few recurring misspellings.
DEMONYMS = {
    "usa": "USA",
    "american": "USA",
    "german": "GER",
    "french": "FRA",
    "polish": "POL",
    "swedish": "SWE",
    "danish": "DEN",
    "turkish": "TUR",
    "greek": "GRE",
    "finnish": "FIN",
    "spanish": "SPR",
    "italian": "ITA",
    "norwegian": "NOR",
    "norweigan": "NOR",
    "ukrainian": "UKR",
    "canadian": "CAN",
    "swiss": "SWI",
    "serbian": "SER",
    "serbain": "SER",
    "kosovar": "KOS",
    "chechen": "CHE",
    "burmese": "BRM",
    "irish": "IRE",
    "palestinian": "PAL",
    "kurdish": "KUR",
    "sierraleonian": "SIE",
    "sierraleonean": "SIE",
}

MIN_SUBSTR_LEN = 4  # shortest country name accepted as an embedded substring

TAG_LINE_RE = re.compile(r'^\s*([A-Z][A-Z0-9]{2})\s*=\s*"countries/(.+?)\.txt"')
HISTORY_NAME_RE = re.compile(r"^([A-Z][A-Z0-9]{2})\s*-\s*(.+)\.txt$")
NUMERIC_PREFIX_RE = re.compile(r"^\d+_")
TOKEN_SPLIT_RE = re.compile(r"[^A-Za-z0-9]+")
COMMIT_MARK = "@@COMMIT@@"

# A country's displayed name depends on its ruling ideology, so the game-start
# name is the loc key '<tag>_<ruling_party_ideology>'. These are the four
# ideology groups; 'ruling_party = X' in a history file picks one.
IDEOLOGY_GROUPS = ("democratic", "communism", "fascism", "neutrality")
RULING_PARTY_RE = re.compile(r"ruling_party\s*=\s*(democratic|communism|fascism|neutrality)")
COSMETIC_TAG_RE = re.compile(r"set_cosmetic_tag\s*=\s*([A-Z][A-Z0-9_]{2,})")
LOC_NAME_RE = re.compile(r'^\s*([A-Za-z0-9_]+):\d*\s*"(.*)"\s*$')
# Country names live here; cosmetic-tag names (e.g. KUR's start cosmetic KDP) here.
NAME_LOC_FILES = ("countries_l_english.yml", "MD_countries_cosmetic_l_english.yml")

# Skipped when counting lines of code (no meaningful line count). Binary content
# is also caught by a NUL-byte check; this list just avoids streaming big assets.
BINARY_EXTS = {
    ".dds", ".tga", ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".ico", ".ogg",
    ".wav", ".mp3", ".flac", ".ttf", ".otf", ".psd", ".mesh", ".xac", ".xsm",
    ".anim", ".lnk", ".xh4prj", ".zip", ".7z", ".exe", ".dll", ".pdb", ".bin", ".dat",
}


def run_git(repo: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "-c", "core.quotepath=false", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed:\n{result.stderr.strip()}")
    return result.stdout


def normalise(text: str) -> str:
    """Lowercase and strip everything that is not a-z/0-9."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def load_country_tags(repo: Path) -> tuple[set[str], dict[str, str]]:
    """Return (valid_tags, name->tag) built from common/country_tags/*.txt."""
    tags: set[str] = set()
    names: dict[str, str] = {}
    tag_dir = repo / "common" / "country_tags"
    for path in sorted(tag_dir.glob("*.txt")):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            m = TAG_LINE_RE.match(line)
            if not m:
                continue
            tag, name = m.group(1), m.group(2)
            tags.add(tag)
            key = normalise(name)
            # First definition wins; country_tags is the authoritative source.
            names.setdefault(key, tag)
    return tags, names


def add_history_names(repo: Path, tags: set[str], names: dict[str, str]) -> None:
    """Add alternate country names from history/countries/'TAG - Name.txt'."""
    hist_dir = repo / "history" / "countries"
    if not hist_dir.is_dir():
        return
    for path in hist_dir.glob("*.txt"):
        m = HISTORY_NAME_RE.match(path.name)
        if not m:
            continue
        tag, name = m.group(1), m.group(2)
        if tag not in tags:
            continue
        names.setdefault(normalise(name), tag)


def load_start_country_names(repo: Path, valid_tags: set[str]) -> dict[str, str]:
    """Return tag -> displayed country name at game start.

    The name shown for a country depends on its ruling ideology (e.g. RAJ is
    'India' at start under neutrality, but 'Delhi Caliphate' under fascism). So
    we read the start ideology from each history file's 'ruling_party', honour a
    'set_cosmetic_tag' override if present, then look up '<base>_<ideology>' in
    the country-name localisation, with sensible fallbacks.
    """
    start_ideology: dict[str, str] = {}
    cosmetic_of: dict[str, str] = {}
    file_name: dict[str, str] = {}  # geographic name from the history filename
    cosmetic_tags: set[str] = set()

    hist_dir = repo / "history" / "countries"
    for path in sorted(hist_dir.glob("*.txt")):
        m = HISTORY_NAME_RE.match(path.name)
        if not m:
            continue
        tag = m.group(1)
        file_name.setdefault(tag, m.group(2))
        text = path.read_text(encoding="utf-8", errors="replace")
        rp = RULING_PARTY_RE.search(text)
        if rp:
            start_ideology.setdefault(tag, rp.group(1))
        cm = COSMETIC_TAG_RE.search(text)
        if cm:
            cosmetic_of.setdefault(tag, cm.group(1))
            cosmetic_tags.add(cm.group(1))

    valid_bases = valid_tags | cosmetic_tags
    by_ideology: dict[tuple[str, str], str] = {}
    bare: dict[str, str] = {}
    for fn in NAME_LOC_FILES:
        path = repo / "localisation" / "english" / fn
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            mm = LOC_NAME_RE.match(line)
            if not mm:
                continue
            key, value = mm.group(1), mm.group(2)
            base, _, suffix = key.rpartition("_")
            if suffix in IDEOLOGY_GROUPS and base in valid_bases:
                by_ideology[(base, suffix)] = value
            elif key in valid_bases:
                bare[key] = value

    result: dict[str, str] = {}
    for tag in valid_tags:
        ideology = start_ideology.get(tag)
        bases = [b for b in (cosmetic_of.get(tag), tag) if b]
        name: str | None = None
        if ideology:
            for base in bases:
                name = by_ideology.get((base, ideology))
                if name:
                    break
        if name is None:  # no start ideology, or no key for it
            for base in bases:
                name = bare.get(base)
                if name:
                    break
                name = next((by_ideology[(base, io)] for io in IDEOLOGY_GROUPS if (base, io) in by_ideology), None)
                if name:
                    break
        result[tag] = name or file_name.get(tag) or tag
    return result


def build_name_matcher(names: dict[str, str], valid_tags: set[str]):
    """Return match(stem_raw) -> tag|None for files in the name-convention dirs.

    Resolution order (first hit wins), designed so the most specific signal
    dominates:
      1. STEM_OVERRIDES  - prefix, fixes word-order cases (korea_north -> NKO)
      2. exact name      - whole normalised stem equals a country name / alias
      3. bare tag        - the stem itself is a tag (national_focus/ALN.txt)
      4. substring       - a country name / alias embedded in the stem, longest
                           wins so 'MD_South Sudan' -> SSD, not SDN
      5. demonym         - prefix match for irregular demonyms (German -> GER)
    """
    # Substring pool: dictionary names + safe aliases, long enough to embed.
    substr_pool = {n: t for n, t in names.items() if len(n) >= MIN_SUBSTR_LEN}
    substr_pool.update(NAME_ALIASES)
    substr_ordered = sorted(substr_pool.items(), key=lambda kv: len(kv[0]), reverse=True)
    demonyms_ordered = sorted(DEMONYMS.items(), key=lambda kv: len(kv[0]), reverse=True)
    exact = {**names, **NAME_ALIASES, **EXACT_ALIASES}

    def match(stem_raw: str) -> str | None:
        stem_nonum = NUMERIC_PREFIX_RE.sub("", stem_raw)  # drop leading '05_', '06_'
        norm = normalise(stem_nonum)
        if not norm:
            return None
        for key, tag in STEM_OVERRIDES.items():
            if norm.startswith(key):
                return tag
        if norm in exact:
            return exact[norm]
        if stem_nonum.upper() in valid_tags:
            return stem_nonum.upper()
        for name, tag in substr_ordered:
            if name in norm:
                return tag
        for demo, tag in demonyms_ordered:
            if norm.startswith(demo):
                return tag
        return None

    return match


def tags_for_path(path: str, valid_tags: set[str], name_match) -> set[str]:
    """All country tags a single changed file path is attributed to."""
    found: set[str] = set()

    # Signal 1: explicit uppercase TAG token anywhere in the path (whole repo).
    for token in TOKEN_SPLIT_RE.split(path):
        if token in valid_tags:
            found.add(token)

    # Signal 2: name/demonym dictionary, restricted to name-convention dirs.
    if path.startswith(NAME_DIRS):
        hit = name_match(Path(path).stem)
        if hit:
            found.add(hit)

    return found


def iter_commits(repo: Path, rev: str, include_merges: bool):
    """Yield lists of changed file paths, one list per commit reachable from rev."""
    args = ["log", rev, "--name-only", f"--format={COMMIT_MARK}%H"]
    if not include_merges:
        args.insert(2, "--no-merges")
    output = run_git(repo, args)

    files: list[str] = []
    started = False
    for line in output.splitlines():
        if line.startswith(COMMIT_MARK):
            if started:
                yield files
            files = []
            started = True
        elif line.strip():
            files.append(line)
    if started:
        yield files


def list_tree_blobs(repo: Path, rev: str) -> list[tuple[str, str]]:
    """Return (blob_sha, path) for every file in rev's tree."""
    out = run_git(repo, ["ls-tree", "-r", "-z", rev])
    blobs: list[tuple[str, str]] = []
    for entry in out.split("\x00"):
        if not entry:
            continue
        meta, _, path = entry.partition("\t")
        parts = meta.split()
        if len(parts) >= 3 and parts[1] == "blob":
            blobs.append((parts[2], path))
    return blobs


def blob_line_counts(repo: Path, shas: list[str]) -> dict[str, int]:
    """Map blob_sha -> newline count via a single `git cat-file --batch`. Blobs
    containing a NUL byte are treated as binary and counted as 0 lines."""
    if not shas:
        return {}
    proc = subprocess.Popen(
        ["git", "-C", str(repo), "cat-file", "--batch"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    out, _ = proc.communicate(("\n".join(shas) + "\n").encode())

    counts: dict[str, int] = {}
    i, n = 0, len(out)
    while i < n:
        nl = out.find(b"\n", i)
        if nl == -1:
            break
        header = out[i:nl].split(b" ")
        i = nl + 1
        if len(header) < 3 or header[1] != b"blob":  # 'missing' line has no body
            continue
        sha, size = header[0].decode(), int(header[2])
        content = out[i : i + size]
        i += size + 1  # body is followed by a trailing newline
        counts[sha] = 0 if b"\x00" in content else content.count(b"\n")
    return counts


def count_lines_of_code(repo: Path, rev: str, tags_of) -> Counter[str]:
    """Sum lines of code per tag across rev's tree, attributing each text file to
    the same tags as the commit counter. Files shared by N tags count for all N."""
    attributed: list[tuple[str, frozenset[str]]] = []
    shas: set[str] = set()
    for sha, path in list_tree_blobs(repo, rev):
        if path[path.rfind(".") :].lower() in BINARY_EXTS:
            continue
        tags = tags_of(path)
        if not tags:
            continue
        attributed.append((sha, tags))
        shas.add(sha)

    line_count = blob_line_counts(repo, sorted(shas))
    loc: Counter[str] = Counter()
    for sha, tags in attributed:
        lines = line_count.get(sha, 0)
        if lines:
            for tag in tags:
                loc[tag] += lines
    return loc


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rev", default="main", help="revision to trawl (default: main)")
    parser.add_argument("--repo", default=".", help="path to the git repo (default: .)")
    parser.add_argument("-o", "--output", help="write CSV here (default: stdout)")
    parser.add_argument("--no-names", action="store_true", help="omit the game-start country-name column")
    parser.add_argument("--no-loc", action="store_true", help="omit the lines-of-code column")
    parser.add_argument("--include-merges", action="store_true", help="also count merge commits")
    parser.add_argument("--min-count", type=int, default=1, help="omit countries below this count")
    parser.add_argument(
        "--report-unmatched",
        action="store_true",
        help="instead of counting, list files in name-dirs that matched no country (for auditing the dictionary)",
    )
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    if not (repo / ".git").exists():
        sys.exit(f"{repo} is not a git repository")

    valid_tags, names = load_country_tags(repo)
    add_history_names(repo, valid_tags, names)
    name_match = build_name_matcher(names, valid_tags)
    tag_to_name = {} if args.no_names else load_start_country_names(repo, valid_tags)

    if args.report_unmatched:
        report_unmatched(repo, args.rev, valid_tags, name_match)
        return

    # Paths recur across thousands of commits; resolve each path's tags once.
    path_cache: dict[str, frozenset[str]] = {}

    def cached_tags(path: str) -> frozenset[str]:
        hit = path_cache.get(path)
        if hit is None:
            hit = frozenset(tags_for_path(path, valid_tags, name_match))
            path_cache[path] = hit
        return hit

    counts: Counter[str] = Counter()
    n_commits = 0
    for files in iter_commits(repo, args.rev, args.include_merges):
        n_commits += 1
        commit_tags: set[str] = set()
        for path in files:
            commit_tags |= cached_tags(path)
        counts.update(commit_tags)

    loc_counts: Counter[str] = Counter() if args.no_loc else count_lines_of_code(repo, args.rev, cached_tags)

    rows = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    rows = [(tag, c) for tag, c in rows if c >= args.min_count]

    def csv_field(value: str) -> str:
        return f'"{value.replace(chr(34), chr(34) * 2)}"' if ("," in value or '"' in value) else value

    lines = []
    for tag, count in rows:
        fields = [tag, str(count)]
        if not args.no_names:
            fields.append(csv_field(tag_to_name.get(tag, tag)))
        if not args.no_loc:
            fields.append(str(loc_counts.get(tag, 0)))
        lines.append(", ".join(fields))
    text = "\n".join(lines) + ("\n" if lines else "")

    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(
            f"Scanned {n_commits} commits from '{args.rev}'. "
            f"Wrote {len(rows)} countries to {args.output}.",
            file=sys.stderr,
        )
    else:
        sys.stdout.write(text)
        print(
            f"\nScanned {n_commits} commits from '{args.rev}'; {len(rows)} countries.",
            file=sys.stderr,
        )


def report_unmatched(repo: Path, rev: str, valid_tags: set[str], name_match) -> None:
    """List the set of name-dir files that no country could be attributed to."""
    unmatched: set[str] = set()
    seen: set[str] = set()
    for files in iter_commits(repo, rev, include_merges=False):
        for path in files:
            if not path.startswith(NAME_DIRS) or path in seen:
                continue
            seen.add(path)
            if not tags_for_path(path, valid_tags, name_match):
                unmatched.add(path)
    for path in sorted(unmatched):
        print(path)
    print(f"\n{len(unmatched)} unmatched name-dir files (likely regional/shared/generic).", file=sys.stderr)


if __name__ == "__main__":
    main()
