# Millennium Dawn Tools

Development tools and scripts used by the Millennium Dawn team for quality assurance, asset management, and mod publishing.

## Requirements

Some scripts rely on non-native packages for Python. The dependency lists live
in `pyproject.toml` under `[dependency-groups]`. Install them from the repo root
(pip 25.1+):

```bash
pip install --group runtime   # requests, pillow (for the scripts that need them)
pip install --group dev       # pytest, coverage, pyyaml, Ruff, Black, Pylint, mypy
```

`python tools/dev_setup.py` installs these for you as part of the dev setup.

Python quality checks run on `tools/` in pre-commit and CI:

```bash
python -m coverage run --branch -m pytest
python -m coverage report
ruff check tools
black --check tools
pylint tools --reports=no --score=no
mypy
```

Black is the canonical formatter. Mypy checks the typed report and validator-core
surfaces declared in `pyproject.toml`; the remaining scripts are migrated in
small, behavior-tested slices rather than hidden behind broad ignores.

## Quick Start

Use `run.py` to run any tool by short name — no need to remember subdirectory paths:

```bash
python3 tools/run.py --list                              # see all available tools
python3 tools/run.py estimate_gdp USA --all              # run a tool by name
python3 tools/run.py find_idea common/ideas/Greek.txt    # partial names work too
python3 tools/run.py publish_workshop release --full      # pass args through
python3 tools/run.py gfx_entry_generator                  # works on any platform
```

## Directory Structure

```
tools/
├── analysis/          Analysis, reference finders, metrics
├── assets/            DDS conversion, GFX generation, texture tools
├── generators/        Content generators (tribute ideas, focus names)
├── linting/           Style checkers, formatters, encoding validators
├── publishing/        Steam Workshop publishing
├── report_lib/        PR validation report renderer + GitHub Checks API client
├── shared/            Test harness helpers and repo-anchored paths
├── standardization/   Auto-standardizers for focuses, events, decisions, ideas
├── tests/             All Python tests for tools/ (root scripts plus domain subdirs)
├── validation/        Content validators (events, decisions, variables, etc.)
├── shared_utils.py    Shared utilities (Colors, FileOpener, path helpers, arg parsers)
├── loc.py             Localisation utilities
├── logging_tool.py    Logging utility
├── precommit_validate.py Pre-commit hook: runs the commit-stage validators in parallel
├── standardize_staged.py Pre-commit hook: routes staged files to standardizers
├── generate_validation_report.py CI: generates PR validation reports
├── validate_tools.py  CI: validates Python scripts in tools/
├── COMMENT_STYLE.md   Comment style for Python tooling (why, not what)
└── README.md
```

### Architecture quick-reference

- **Writing a new validator?** Subclass `BaseValidator` from `tools/validation/validator_common.py`. Prefer `add_error(category, msg, file, line)` for structured issues; `_report(list_of_strings, ...)` still works and now auto-parses common `path:line - msg` formats into file+line for the PR comment's inline annotations.
- **Writing a new linter or fixer?** Import helpers from `tools/shared_utils.py`. Skip `validator_common` — linters don't emit the structured issue stream validators produce.
- **Reading validator output?** Import from `tools/report_lib`. It parses the JSON sidecars each validator writes and renders the PR comment + GitHub Check Runs.
- **Writing comments?** See [COMMENT_STYLE.md](COMMENT_STYLE.md). Default to none; add one when the _why_ is non-obvious.

### Writing a new validator

1. Create `tools/validation/validate_<topic>.py`.
2. Subclass `BaseValidator` from `validator_common`. Implement `run_validations(self, files: List[str]) -> None`.
3. Use `self.add_error(category, message, file, line)` for structured issues. The PR report renderer picks these up for inline annotations.
4. Use `DEFAULT_EXTRA_SKIP_PATTERNS` from `validator_common` for `EXTRA_SKIP_PATTERNS` (extend with domain-specific patterns if needed).
5. Wire into CI: add an entry to `.github/workflows/coding-pipeline.yml` in the `validate-core` or `validate-targeted` matrix. This is the gate for most validators — they run CI-only.
6. Decide if it should also run on `git commit`. Heavy cross-reference validators stay CI-only. A fast validator can join the commit-stage set: add it to the `_REGISTRY` in `tools/precommit_validate.py` (with its path rules and `--strict` flag) and pin its selection in `tools/tests/precommit_validate_test.py`. The `config_drift_test` enforces that every validator runs on pre-commit or CI.
7. Add tests in `tools/tests/validation/`.

```python
#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import disk_cache
from validator_common import (
    BaseValidator,
    Colors,
    DEFAULT_EXTRA_SKIP_PATTERNS,
    Severity,
    run_validator_main,
    should_skip_file,
)

EXTRA_SKIP_PATTERNS = DEFAULT_EXTRA_SKIP_PATTERNS


class MyValidator(BaseValidator):
    def run_validations(self, files):
        for path in files:
            if should_skip_file(path, EXTRA_SKIP_PATTERNS):
                continue
            content = disk_cache.per_file_cached_by_content(
                self.mod_path, "my_ns", path, Path(path).read_text(encoding="utf-8"),
                lambda: self._validate_file(path),
            )
            # results already stored via add_error inside _validate_file

    def _validate_file(self, path):
        # ... validation logic ...
        self.add_error("my_category", "Something is wrong", path, line=42)


if __name__ == "__main__":
    run_validator_main(MyValidator, "My custom validation")
```

### Common imports from `shared_utils`

| Symbol                           | Use                                                         |
| -------------------------------- | ----------------------------------------------------------- |
| `Colors`                         | ANSI color constants (`GREEN`, `RED`, `YELLOW`, etc.)       |
| `DEFAULT_EXTRA_SKIP_PATTERNS`    | `["FR_loc"]` — base skip patterns for validators            |
| `clean_filepath(path)`           | Trim absolute path to start from `common/`, `events/`, etc. |
| `should_skip_file(path, extra)`  | Check if a file matches skip patterns                       |
| `strip_comments(text)`           | Remove `#`-comments from HOI4 script text                   |
| `FileOpener`                     | LRU-cached file reader (8192 entries)                       |
| `create_validation_parser(desc)` | Argparse factory for validators (flags below)               |
| `create_linting_parser(desc)`    | Argparse factory for linting scripts (flags below)          |
| `run_validator_main(cls, desc)`  | Entry point: parses args, builds instance, runs, exits      |

Details:

- `create_validation_parser`: `--path`, `--strict`, `--staged`, `--no-cache`, `--workers`.
- `create_linting_parser`: `--mode`, `--files`, `--workers`.

## Scripts by Category

### Linting (`linting/`)

Style checkers, formatters, and encoding validators. These are used in pre-commit hooks and CI.

| Script                                | Description                                       |
| ------------------------------------- | ------------------------------------------------- |
| **check_common_mistakes.py**          | Common scripting-mistake detector (see below)     |
| **fix_styling.py**                    | Auto-fixer for tabs, spacing, braces, whitespace  |
| **fix_line_endings.py**               | Converts CRLF to LF line endings                  |
| **fix_loc_yaml.py**                   | Fixes loc YAML quotes, tabs, colons, version keys |
| **validate_localization_encoding.py** | Validates and fixes UTF-8 BOM for loc files       |
| **validate_mod_encoding.py**          | Checks UTF-8 encoding for `.mod` files            |

Details:

- `check_common_mistakes.py` covers bad value ranges, `allowed`/`cancel` no-ops, `ai_will_do factor` vs `base`, division instead of multiplication, and malformed leader rotations in `*_political_leaders.txt`.
- `--output FILE` also writes the `FILE`-stem `.json` sidecar the CI validation report reads.

### Validation (`validation/`)

Content validators run in CI via matrix strategy. See `validation/README.md` for the full list and check details.

`validate_common_mistakes.py` owns the fast scripting checks formerly run as a
separate lint hook. The linting module remains its implementation library and
direct compatibility entry point.

### Standardization (`standardization/`)

Auto-standardizers for focus trees, events, decisions, and ideas. See `standardization/README.md` for details.

### Assets (`assets/`)

DDS conversion, GFX entry generation, texture and flag tools.

| Script                         | Description                                         |
| ------------------------------ | --------------------------------------------------- |
| **batchdds-2.py**              | Self-contained DDS converter (DXT1/DXT5, no deps)   |
| **convert_to_legacy_dds.py**   | Converts DX10/sRGB DDS to legacy ARGB8888 for HOI4  |
| **duplicate_icon.py**          | Detects duplicate icon files in a focus tree file   |
| **find_duplicate_textures.py** | Finds duplicate texture files in the mod            |
| **flag-reference-checker.py**  | Validates flag references across the mod            |
| **gfx_entry_generator_gui.py** | GUI front end for the root `gfx_entry_generator.py` |
| **state_gfx.py**               | Renders state-file province colors onto the map     |

### Analysis (`analysis/`)

Metrics, reference analysis, and review tools.

| Script                              | Description                                               |
| ----------------------------------- | --------------------------------------------------------- |
| **ai_path_report.py**               | One country's AI path rule and wiring (issue #3162)       |
| **calculate_days.py**               | Calculates days from January 1st for the HOI4 date system |
| **estimate_gdp.py**                 | Estimates starting GDP from MD's building formulas        |
| **event_load.py**                   | Yearly-pulse event load for one country, by year          |
| **find_idea_references.py**         | Finds which ideas from a file are used elsewhere          |
| **find_scripted_loc_references.py** | Checks whether scripted loc names are referenced          |
| **pre_place_power_plants.py**       | Bakes power-plant counts into `history/states/`           |
| **review_branch.py**                | Generates a diff summary of the current branch vs main    |
| **search_add_ideas.py**             | Finds `add_ideas` / `add_timed_idea` usage                |

Details:

- `ai_path_report.py` also covers flag wiring, focus ownership, killswitch orphans, and the burdens/mechanics the AI must be able to resolve.
- `event_load.py` flags years where several events land in the same window.
- `pre_place_power_plants.py` bakes `fossil_powerplant` + `composite_plant` counts to skip startup loops; re-run after edits to the energy formula or country/state setup.

### Generators (`generators/`)

Content generation tools.

| Script                        | Description                                       |
| ----------------------------- | ------------------------------------------------- |
| **generate_tribute_ideas.py** | Generates tribute ideas and loc for all countries |

### Publishing (`publishing/`)

| Script                  | Description                                               |
| ----------------------- | --------------------------------------------------------- |
| **publish_workshop.py** | Publishes the mod to the Steam Workshop (release or beta) |

See the [Workshop Publishing Guide](#workshop-publishing-guide) below for full usage details.

### Report Library (`report_lib/`)

Internal package used by `generate_validation_report.py` to render PR comments and post GitHub Check Runs. Its only inputs are the JSON sidecars produced by each validator.

| Module            | Responsibility                                                          |
| ----------------- | ----------------------------------------------------------------------- |
| **models.py**     | `Issue`, `ValidatorRun`, `ReportContext` dataclasses                    |
| **loader.py**     | Reads `.json` sidecars; falls back to parsing `.log` text when missing  |
| **dedupe.py**     | Collapses cross-validator duplicates, preserving first-seen order       |
| **markdown.py**   | Renders the report Markdown — summary table + issues-by-file + raw logs |
| **truncation.py** | Drops heavy sections when the body exceeds 60 KB, keeping the summary   |
| **comment.py**    | Find-by-marker + PATCH/POST logic for the bot-authored PR comment       |
| **checks_api.py** | One Check Run per validator with up to 50 annotations per run           |

Tests live in `tests/report_lib/` and run on every PR via the `tools-validation.yml` workflow.

### Tests (`tests/`)

| Script                             | Description                                                 |
| ---------------------------------- | ----------------------------------------------------------- |
| **staged_validators_test.py**      | Tests staged validators using synthetic temp files          |
| **staged_validators_real_test.py** | Tests staged validators on real mod files with known issues |

Tests for individual validators live in `tests/validation/`:

| Script                               | Description                                        |
| ------------------------------------ | -------------------------------------------------- |
| **all_validators_test.py**           | Smoke test: every validator loads and runs clean   |
| **validate_simplifications_test.py** | Scope-merge and two-bucket `random_list` detectors |

Details:

- `all_validators_test.py`: every `validate_*.py` must expose a `BaseValidator` subclass and run cleanly on an empty mod tree.
- `validate_simplifications_test.py` covers suppression edge cases.

### Root-Level Scripts

Hook entry points, CI tools, shared libraries, and other scripts that stay at the `tools/` root.

| Script                            | Description                                              |
| --------------------------------- | -------------------------------------------------------- |
| **precommit_validate.py**         | Pre-commit hook `md-validate-content` (parallel)         |
| **standardize_staged.py**         | Pre-commit hook: routes staged files to standardizers    |
| **generate_validation_report.py** | CI: PR validation comment + GitHub Check Runs            |
| **validate_tools.py**             | CI: validates Python scripts in the tools directory      |
| **gfx_entry_generator.py**        | Cross-platform GFX entry generator; merges into `.gfx`   |
| **shared_utils.py**               | Shared utilities — see the imports table above           |
| **loc.py**                        | Localisation utilities                                   |
| **logging_tool.py**               | Logging utility                                          |
| **cleanup_or.py**                 | Finds redundant `AND` / single-condition `OR` blocks     |
| **assign_mio_icons.py**           | Manual: MIO trait icons from the winning modifier        |
| **summarize_game_log.py**         | Manual: scripted `log =` lines from game.log to a report |
| **sync_dynamic_tokens.py**        | Manual: regenerates synchronized dynamic tokens          |

Details:

- `precommit_validate.py` shares one staged-file list across the validators it runs.
- `shared_utils.py` also exports `create_standard_parser`, `run_tool_main`, `find_hoi4_install()` and `extract_block_from_text()`.
- `cleanup_or.py` is a library for `linting/check_common_mistakes.py`, not a standalone tool.
- `assign_mio_icons.py` assigns icons deterministically from the trait's winning modifier.
- `summarize_game_log.py` produces a "what happened" report after a test run.
- `sync_dynamic_tokens.py` regenerates `common/synchronized_dynamic_tokens` from error.log.

---

## Workshop Publishing Guide

`publishing/publish_workshop.py` handles uploading the mod to the Steam Workshop. It supports two targets (**release** and **beta**) and two modes (**full upload** and **diff-only upload**).

### Prerequisites

- **SteamCMD** must be installed and either on your `PATH` or in one of the standard locations (`/usr/bin/steamcmd`, `C:\steamcmd\steamcmd.exe`, etc.).
- A Steam account with publish permissions on the Workshop items.

### Authentication

Provide your Steam username in one of two ways:

```bash
# Via environment variable
export STEAM_USERNAME=YourSteamUser

# Or via CLI flag
python3 tools/publishing/publish_workshop.py release --full --username YourSteamUser
```

SteamCMD will prompt for your password and Steam Guard code interactively.

### Usage

#### Full Upload (release)

Uploads the entire mod (minus dev/CI files) to the release Workshop item:

```bash
python3 tools/publishing/publish_workshop.py release --full
```

#### Full Upload (beta)

Same as above but targets the beta Workshop item:

```bash
python3 tools/publishing/publish_workshop.py beta --full
```

#### Diff-Only Upload (beta)

Uploads only files changed since a given git ref. Useful for pushing incremental beta updates without re-uploading the entire mod:

```bash
python3 tools/publishing/publish_workshop.py beta --base-ref v1.12.3b
```

The script uses `git log --diff-filter=ACM` to determine which files changed, copies the full repo, then prunes unchanged files before uploading. `descriptor.mod` and `thumbnail.png` are always included.

### What Gets Excluded

The following are automatically excluded from all uploads:

`.git`, `.github`, `.claude`, `.vscode`, `docs`, `tools`, `resources`, `scenario_tests`, `CLAUDE.md`, `CONTRIBUTING.md`, `CODEOWNERS`, `README.md`, `Changelog.txt`, `Millennium_Dawn.mod`, and other dev/CI artifacts.

Use `--exclude PATTERN` to add extra exclusions, or `--no-default-excludes` to skip the built-in list entirely.

### Options Reference

| Flag                    | Description                                                            |
| ----------------------- | ---------------------------------------------------------------------- |
| `release` / `beta`      | Which Workshop item to target                                          |
| `--full`                | Upload the entire mod                                                  |
| `--base-ref REF`        | Upload only files changed since REF (mutually exclusive with `--full`) |
| `--username USER`       | Steam username (default: `$STEAM_USERNAME`)                            |
| `--mod-id ID`           | Override the default Workshop mod ID                                   |
| `--exclude PATTERN`     | Extra exclude pattern (repeatable)                                     |
| `--no-default-excludes` | Skip the built-in exclude list                                         |

### Workshop Mod IDs

| Target  | Mod ID       |
| ------- | ------------ |
| release | `2777392649` |
| beta    | `3374271790` |

## Old Folder

The `old/` directory contains unused or outdated tools kept for historical reference. They are not expected to be used in current development.
