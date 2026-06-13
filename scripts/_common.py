"""Shared helpers for the read-only phase-workflow scripts.

Stdlib-only. No side effects beyond reading git state and repo files. None of
these helpers stage, commit, push, or mutate any file.
"""
from __future__ import annotations

import fnmatch
import re
import subprocess
from pathlib import Path

# AI_USAGE.md required subsections (heading substring → human label).
REQUIRED_SECTIONS = [
    ("AI Tools and Models Used", "tools used"),
    ("Important Prompts", "important prompts"),
    ("Decisions Made with AI Assistance", "decisions"),
    ("Validation Commands Run", "validation commands and results"),
    ("Manual Review Performed", "manual review"),
    ("Review Findings or Mistakes Caught", "mistakes / review findings"),
    ("Deferred or Blocked Work", "deferred or blocked work"),
    ("Architectural or Specification Amendments", "amendments"),
]

PLACEHOLDER_TOKENS = ("_(fill in)_", "fill in when", "> fill in")

# Directories whose untracked contents are almost certainly local-only scratch.
LOCAL_ONLY_DIRS = ("_bmad-output", "review_docs", "data", "notes", "scratch", "prompts", ".local")


def repo_root() -> Path:
    """Return the git toplevel, falling back to cwd if git is unavailable."""
    code, out, _ = _run(["git", "rev-parse", "--show-toplevel"])
    if code == 0 and out.strip():
        return Path(out.strip())
    return Path.cwd()


def _run(args: list[str]) -> tuple[int, str, str]:
    """Run a command read-only and capture output. Used only for git queries."""
    proc = subprocess.run(args, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def git(*args: str) -> tuple[int, str, str]:
    """Run a read-only git query (status/diff/etc.) from the repo root."""
    return _run(["git", "-C", str(repo_root()), *args])


def is_git_repo() -> bool:
    code, out, _ = git("rev-parse", "--is-inside-work-tree")
    return code == 0 and out.strip() == "true"


def read_ai_usage() -> str | None:
    path = repo_root() / "AI_USAGE.md"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def parse_phase(phase: str) -> tuple[str | None, list[int]]:
    """Normalize a PHASE token to (story_id, units).

    'S2_UNIT_1_2' -> ('S2', [1, 2]); 'S2_UNIT_3' -> ('S2', [3]); 'S2' -> ('S2', []).
    Returns (None, []) if no story id is recognizable.
    """
    if not phase:
        return None, []
    text = phase.strip().upper()
    m = re.match(r"^(S\d+)(?:_UNIT_([\d_]+))?$", text)
    if not m:
        return None, []
    story = m.group(1)
    units = [int(u) for u in m.group(2).split("_") if u] if m.group(2) else []
    return story, units


def extract_story_block(text: str, story_id: str) -> str | None:
    """Return the AI_USAGE slice for '### Story: S{n} — …' up to the next '### ' / EOF."""
    lines = text.splitlines()
    start = None
    pattern = re.compile(rf"^### Story:\s*{re.escape(story_id)}\b", re.IGNORECASE)
    for i, line in enumerate(lines):
        if pattern.match(line):
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("### "):
            end = j
            break
    return "\n".join(lines[start:end])


def section_status(block: str) -> dict[str, tuple[bool, bool]]:
    """For each required section return (present, filled)."""
    result: dict[str, tuple[bool, bool]] = {}
    for heading, _label in REQUIRED_SECTIONS:
        body = _section_body(block, heading)
        present = body is not None
        filled = bool(body and not _is_placeholder(body))
        result[heading] = (present, filled)
    return result


def _section_body(block: str, heading: str) -> str | None:
    """Return text under '#### <heading>' up to the next '#### '/'### '/EOF, or None."""
    lines = block.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith("#### ") and heading.lower() in line.lower():
            start = i + 1
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start, len(lines)):
        if lines[j].startswith("#### ") or lines[j].startswith("### "):
            end = j
            break
    return "\n".join(lines[start:end]).strip()


def _is_placeholder(body: str) -> bool:
    low = body.lower()
    if not low.strip():
        return True
    return any(tok in low for tok in PLACEHOLDER_TOKENS)


def unit_status(block: str, n: int) -> str:
    """Classify a unit as 'worked', 'not_started', or 'unknown' within a story block.

    'worked'      — a singular '**Unit N —/-/:' decision marker exists (documented work).
    'not_started' — the unit (incl. 'N+') is named on a line with a deferral keyword.
    """
    if re.search(rf"\*\*Unit\s+0*{n}(?!\d)\s*[—\-:]", block):
        return "worked"
    deferral = re.compile(r"not started|deferred|awaiting|not yet|not begun", re.IGNORECASE)
    unit_ref = re.compile(rf"\bUnits?\s*0*{n}(?!\d)\+?")
    for line in block.splitlines():
        if unit_ref.search(line) and deferral.search(line):
            return "not_started"
    return "unknown"


def gitignore_patterns() -> list[str]:
    path = repo_root() / ".gitignore"
    if not path.exists():
        return []
    patterns = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            patterns.append(line)
    return patterns


def matches_gitignore(rel_path: str, patterns: list[str]) -> bool:
    """Best-effort fnmatch against .gitignore patterns (dir and glob forms)."""
    parts = rel_path.split("/")
    for pat in patterns:
        p = pat.rstrip("/")
        if pat.endswith("/"):
            # directory pattern: match if any path segment equals it
            if p in parts:
                return True
        if fnmatch.fnmatch(rel_path, p) or fnmatch.fnmatch(rel_path, f"{p}/*"):
            return True
        if any(fnmatch.fnmatch(seg, p) for seg in parts):
            return True
    return False


def likely_local_only(rel_path: str, patterns: list[str]) -> str | None:
    """Return a reason string if an untracked path looks local-only, else None."""
    if matches_gitignore(rel_path, patterns):
        return "matches .gitignore"
    top = rel_path.split("/")[0]
    if top in LOCAL_ONLY_DIRS:
        return f"under local-only dir '{top}/'"
    # Root-level planning/scratch markdown (kept out of fresh clones).
    if "/" not in rel_path and rel_path.endswith(".md"):
        stem = rel_path[:-3].upper()
        if any(tag in stem for tag in ("_PLAN", "PLAN_", "_LOG", "_WALKTHROUGH", "STUDY_GUIDE", "ROADMAP", "SCRATCH")):
            return "root-level planning/scratch markdown"
    return None
