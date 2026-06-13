"""make ai-usage-check PHASE=S2_UNIT_3 — gate an AI_USAGE.md phase entry.

READ-ONLY. Never edits AI_USAGE.md. Reports required-section completeness and
per-unit status; prints advisory notes for TDD evidence, review tier, and the
ce-compound decision.

Exit codes:
  0  all required sections filled AND all requested units documented as worked
  1  a required section is missing/placeholder, OR a requested unit is not started
  2  unknown phase / story entry not found / AI_USAGE.md absent
"""
import argparse
import os
import re
import sys

import _common as c

REVIEW_KEYWORDS = ("ce-adversarial-reviewer", "ce-code-review", "closeout", "human review", "human")
TDD_KEYWORDS = ("tdd", "test-first", "red → green", "red->green", "failing test")
COMPOUND_KEYWORDS = ("/ce-compound", "ce-compound", "docs/solutions", "compound learning")


def _advisory(block: str) -> None:
    low = block.lower()
    review = [k for k in REVIEW_KEYWORDS if k in low]
    print("\n--- Advisory (reported, does not affect exit code) ---")
    print(f"  review tier mentioned:   {', '.join(review) if review else 'NONE detected'}")
    print(f"  TDD evidence present:    {'yes' if any(k in low for k in TDD_KEYWORDS) else 'no'}")
    print(f"  ce-compound / learnings: {'yes' if any(k in low for k in COMPOUND_KEYWORDS) else 'not recorded'}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", default=os.environ.get("PHASE", ""))
    args = parser.parse_args()

    story, units = c.parse_phase(args.phase)
    if not story:
        print(f"Unrecognized PHASE '{args.phase}'. Use e.g. S2, S2_UNIT_3, S2_UNIT_1_2.")
        return 2

    text = c.read_ai_usage()
    if text is None:
        print("AI_USAGE.md not found at repo root.")
        return 2

    block = c.extract_story_block(text, story)
    if block is None:
        print(f"No '### Story: {story} — …' entry found in AI_USAGE.md.")
        return 2

    unit_label = f" (units {', '.join(map(str, units))})" if units else ""
    print(f"=== AI_USAGE check: {story}{unit_label} ===\n")

    # --- Required sections ---
    statuses = c.section_status(block)
    missing = []
    print("Required sections:")
    for heading, _label in c.REQUIRED_SECTIONS:
        present, filled = statuses[heading]
        mark = "PASS" if filled else ("EMPTY/PLACEHOLDER" if present else "MISSING")
        print(f"  [{mark:>16}] {heading}")
        if not filled:
            missing.append(heading)

    # --- Per-unit status ---
    not_ready_units = []
    if units:
        print("\nRequested unit status:")
        for n in units:
            st = c.unit_status(block, n)
            print(f"  Unit {n}: {st.replace('_', ' ').upper()}")
            if st != "worked":
                not_ready_units.append(n)

    _advisory(block)

    # --- Verdict ---
    print("\n--- Verdict ---")
    if not_ready_units:
        print(f"  Units {not_ready_units} are NOT documented as worked — nothing to gate yet.")
        return 1
    if missing:
        print(f"  {len(missing)} section(s) need attention: {', '.join(missing)}")
        return 1
    print("  All required sections filled and requested units documented. PASS.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
