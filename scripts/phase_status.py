"""make phase-status — read-only snapshot of the working tree for a phase.

Prints staged/modified/untracked files, a diff stat, and flags untracked paths
that look local-only (gitignored or planning/scratch). Never mutates anything.
"""
import sys

import _common as c


def _porcelain() -> list[tuple[str, str]]:
    code, out, _ = c.git("status", "--porcelain")
    if code != 0:
        return []
    entries = []
    for line in out.splitlines():
        if len(line) < 4:
            continue
        entries.append((line[:2], line[3:]))
    return entries


def main() -> int:
    if not c.is_git_repo():
        print("Not a git repository — phase-status needs git.")
        return 1

    entries = _porcelain()
    staged, modified, untracked = [], [], []
    for code_xy, path in entries:
        x, y = code_xy[0], code_xy[1]
        if code_xy == "??":
            untracked.append(path)
        else:
            if x != " " and x != "?":
                staged.append(path)
            if y != " " and y != "?":
                modified.append(path)

    print("=== Phase Status ===\n")

    print(f"Staged ({len(staged)}):")
    for p in staged:
        print(f"  + {p}")
    print(f"\nModified, unstaged ({len(modified)}):")
    for p in modified:
        print(f"  M {p}")
    print(f"\nUntracked ({len(untracked)}):")
    for p in untracked:
        print(f"  ? {p}")

    print("\n--- diff --stat (working + staged) ---")
    _, stat, _ = c.git("diff", "--stat", "HEAD")
    print(stat.rstrip() or "  (no changes vs HEAD)")

    patterns = c.gitignore_patterns()
    flagged = [(p, c.likely_local_only(p, patterns)) for p in untracked]
    flagged = [(p, r) for p, r in flagged if r]
    print(f"\n--- Likely local-only ({len(flagged)}) — do NOT commit without review ---")
    if not flagged:
        print("  (none)")
    for p, reason in flagged:
        print(f"  ! {p}  ({reason})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
