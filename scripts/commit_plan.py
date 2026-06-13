"""make commit-plan — suggest single-responsibility commit groupings.

READ-ONLY and advisory. Never runs git add/commit/push. Prints buckets plus the
exact `git add` command for the human to run themselves.
"""
import re
import sys
from pathlib import Path

import _common as c

SECRET_NAME_PATTERNS = (".env", ".pem", ".key", "id_rsa", "credentials")
SECRET_NAME_GLOBS = ("*.db", "*.db-shm", "*.db-wal")
SECRET_PREFIXES = ("sk-ant-", "sk-", "AKIA", "ghp_", "xoxb-", "-----BEGIN")
CONFIG_NAMES = ("pyproject.toml", "Makefile", ".gitignore", "package.json", "package-lock.json", "tsconfig.json")
CONFIG_SUFFIXES = (".toml", ".ini", ".cfg", ".lock")
TEXT_SUFFIXES = (".py", ".md", ".txt", ".toml", ".ini", ".cfg", ".json", ".ts", ".tsx", ".js", ".yaml", ".yml", ".sh")
MAX_SCAN_BYTES = 200_000


def _changed_paths() -> list[str]:
    code, out, _ = c.git("status", "--porcelain")
    if code != 0:
        return []
    paths = []
    for line in out.splitlines():
        if len(line) >= 4:
            paths.append(line[3:])
    return paths


def _is_secret_name(path: str) -> bool:
    name = path.split("/")[-1]
    if any(tok in name for tok in SECRET_NAME_PATTERNS):
        return True
    import fnmatch
    return any(fnmatch.fnmatch(name, g) for g in SECRET_NAME_GLOBS)


def _secret_prefix_hits(path: str) -> int:
    """Count obvious secret-prefix matches WITHOUT ever returning the value."""
    p = c.repo_root() / path
    if not p.is_file() or p.suffix not in TEXT_SUFFIXES or p.stat().st_size > MAX_SCAN_BYTES:
        return 0
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return 0
    return sum(len(re.findall(re.escape(pref), text)) for pref in SECRET_PREFIXES)


def _bucket(paths: list[str], patterns: list[str]) -> dict[str, list[str]]:
    buckets = {"local": [], "secret": [], "config": [], "docs": [], "source_tests": []}
    for path in paths:
        if c.likely_local_only(path, patterns):
            buckets["local"].append(path)
        elif _is_secret_name(path):
            buckets["secret"].append(path)
        elif path.split("/")[-1] in CONFIG_NAMES or Path(path).suffix in CONFIG_SUFFIXES:
            buckets["config"].append(path)
        elif Path(path).suffix == ".md" or path.startswith("docs/"):
            buckets["docs"].append(path)
        else:
            buckets["source_tests"].append(path)
    return buckets


def _print_group(title: str, subject: str, files: list[str]) -> None:
    if not files:
        return
    print(f"\n### {title}")
    print(f"  suggested subject: {subject}")
    for f in files:
        print(f"    - {f}")
    print(f"  to stage:  git add {' '.join(files)}")


def main() -> int:
    if not c.is_git_repo():
        print("Not a git repository — commit-plan needs git.")
        return 1

    paths = _changed_paths()
    if not paths:
        print("Working tree clean — nothing to plan.")
        return 0

    patterns = c.gitignore_patterns()
    b = _bucket(paths, patterns)

    print("=== Commit Plan (suggestions only — nothing is staged) ===")

    if b["local"]:
        print("\n### Local-only / generated — DO NOT COMMIT")
        for f in b["local"]:
            print(f"    ! {f}  ({c.likely_local_only(f, patterns)})")

    if b["secret"]:
        print("\n### Suspicious secrets / local state — DO NOT COMMIT, review + rotate if needed")
        for f in b["secret"]:
            print(f"    !! {f}")

    # Light prefix scan over committable text files (never prints the value).
    scannable = b["config"] + b["docs"] + b["source_tests"]
    hits = [(f, _secret_prefix_hits(f)) for f in scannable]
    hits = [(f, n) for f, n in hits if n]
    if hits:
        print("\n### Secret-prefix matches in committable files (filename + count only)")
        for f, n in hits:
            print(f"    ?? {f}: {n} match(es) — verify no real secret before committing")

    _print_group("Config", "chore: update project configuration", b["config"])
    _print_group("Docs / process", "docs: update documentation", b["docs"])
    _print_group("Source + tests", "feat: <describe the logical change>", b["source_tests"])

    _print_pairings(b["source_tests"])
    return 0


def _print_pairings(files: list[str]) -> None:
    src = [f for f in files if "/app/" in f and f.endswith(".py")]
    tests = [f for f in files if "/tests/" in f and f.endswith(".py")]
    if not (src and tests):
        return
    print("\n  note: source + test stems for pairing review:")
    for s in src:
        stem = Path(s).stem
        matched = [t for t in tests if stem in Path(t).stem or Path(t).stem.replace("test_", "") in stem]
        label = ", ".join(matched) if matched else "(no name-matched test — pair manually)"
        print(f"    {s}  ->  {label}")


if __name__ == "__main__":
    sys.exit(main())
