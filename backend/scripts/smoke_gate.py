"""AC-4 smoke gate — verifies the real Goose ACP server produces a tool_call event.

Run via: make smoke-goose (from project root) or python3 backend/scripts/smoke_gate.py.
Saves captured frames to data/smoke/frames.json for use as test fixtures.
"""
import asyncio
import json
import logging
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))

from app.adapters.acp_goose import AcpGooseAdapter
from app.adapters.base import TaskInput

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("smoke_gate")

GOOSE_PORT = int(os.getenv("GOOSE_PORT", "3284"))
SMOKE_DIR = os.path.join(os.path.dirname(__file__), "../../data/smoke")
ARTIFACT_PATH = os.path.join(SMOKE_DIR, "smoke_artifact.txt")
FRAMES_PATH = os.path.join(SMOKE_DIR, "frames.json")


async def run_gate() -> None:
    os.makedirs(SMOKE_DIR, exist_ok=True)

    print("\n=== Yuno Smoke Gate (AC-4) ===\n")

    # 1. Start Goose
    provider = os.getenv("GOOSE_PROVIDER", "anthropic")
    model = os.getenv("GOOSE_MODEL", "claude-sonnet-4-5")
    api_key = os.getenv("ANTHROPIC_API_KEY", "")

    if not api_key or api_key == "sk-ant-replace-me":
        print("FAIL: ANTHROPIC_API_KEY not set in .env — cannot run native provider smoke gate")
        sys.exit(1)
    if not api_key.startswith("sk-ant-"):
        print("FAIL: ANTHROPIC_API_KEY in .env does not look like an Anthropic key")
        print("      Expected value to start with sk-ant- (not the variable name or a placeholder).")
        sys.exit(1)

    print(f"[1] Starting goose serve on :{GOOSE_PORT} (provider={provider}, model={model})")
    goose_env = {**os.environ, "GOOSE_PROVIDER": provider, "GOOSE_MODEL": model}
    goose_proc = subprocess.Popen(
        ["goose", "serve", "--host", "127.0.0.1", "--port", str(GOOSE_PORT), "--with-builtin", "developer"],
        env=goose_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    await asyncio.sleep(2)

    if goose_proc.poll() is not None:
        print("FAIL: goose serve exited immediately — check GOOSE_PORT or binary")
        sys.exit(1)

    print("[1] Goose started (pid={})".format(goose_proc.pid))

    captured_events: list[dict] = []

    try:
        # 2. Health check
        import httpx
        async with httpx.AsyncClient(timeout=5) as client:
            for attempt in range(10):
                try:
                    r = await client.get(f"http://127.0.0.1:{GOOSE_PORT}/health")
                    if r.status_code == 200:
                        break
                except Exception:
                    pass
                await asyncio.sleep(0.5)
            else:
                print("FAIL: Goose did not become healthy within 5 seconds")
                sys.exit(1)
        print("[2] Goose health: OK")

        # 3. ACP session + prompt
        task_prompt = (
            f"Write exactly one line of text to the file {ARTIFACT_PATH}: "
            f"'smoke-gate-ok'. Then confirm you wrote it."
        )
        task_input = TaskInput(
            context_preamble="## Role\nSmoke gate verifier — Yuno\n\n## Instructions\nYou write a single file to disk when asked.",
            task_content=task_prompt,
            model=model,
            extensions=["developer"],
            max_turns=5,
            timeout_seconds=120,
        )

        async def capture_event(event: dict) -> None:
            captured_events.append(event)
            print(f"    event: {event.get('type')} — {json.dumps(event.get('data', {}))[:120]}")

        print("[3] Opening ACP session and sending prompt…")
        adapter = AcpGooseAdapter(port=GOOSE_PORT)
        result = await asyncio.wait_for(
            adapter.invoke(task_input, capture_event),
            timeout=120,
        )
        print("[3] Session closed cleanly")

        # 4. Verify tool_call captured
        tool_calls = [e for e in captured_events if e.get("type") == "tool_call"]
        if not tool_calls:
            print("\nFAIL: No tool_call event captured.")
            print(f"      Captured {len(captured_events)} events total: {[e.get('type') for e in captured_events]}")
            print("      This may mean the CLI-bridge provider was used instead of native anthropic.")
            print("      Check GOOSE_PROVIDER=anthropic and ANTHROPIC_API_KEY in .env")
            sys.exit(1)
        print(f"[4] tool_call captured: {tool_calls[0]['data']}")

        # 5. Verify on-disk artifact
        if not os.path.exists(ARTIFACT_PATH):
            print(f"\nFAIL: artifact not written to {ARTIFACT_PATH}")
            sys.exit(1)
        with open(ARTIFACT_PATH) as f:
            content = f.read()
        if "smoke-gate-ok" not in content:
            print(f"\nFAIL: artifact content unexpected: {content!r}")
            sys.exit(1)
        print(f"[5] On-disk artifact verified: {ARTIFACT_PATH!r}")

        # 6. Save frames for test fixtures
        frames = {
            "events": captured_events,
            "result": {
                "output": result.output,
                "tokens_total": result.tokens_total,
                "session_id": result.session_id,
            },
        }
        with open(FRAMES_PATH, "w") as f:
            json.dump(frames, f, indent=2)
        print(f"[6] Frames saved to {FRAMES_PATH}")

        print(f"\n=== SMOKE GATE PASSED ===")
        print(f"    tool_calls:   {len(tool_calls)}")
        print(f"    tokens_total: {result.tokens_total}")
        print(f"    output[:120]: {result.output[:120]!r}")

    finally:
        goose_proc.terminate()
        goose_proc.wait(timeout=5)


if __name__ == "__main__":
    asyncio.run(run_gate())
