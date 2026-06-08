"""
Phase 2 - Example 4: Programmatic Persistence Demo
====================================================

This script demonstrates how to wire a DatabaseSessionService into a Runner
so that session state survives across process restarts.

Run this script twice to see persistence in action:

  # First run — creates the session and stores state
  uv run python phase_2/persistence/run_with_persistence.py

  # Second run — resumes the same session; state is preserved
  uv run python phase_2/persistence/run_with_persistence.py

How to Read This Script:
------------------------
  1. We create a Runner with DatabaseSessionService (SQLite backed).
  2. We create OR RESUME a session using a fixed session ID.
  3. We run a multi-turn conversation, writing state in each turn.
  4. Between turns, we print the full session state to show what persisted.
  5. On the second run of the script, the session already exists in the DB,
     state is restored, and user: / app: scoped values are visible immediately.

Session Lifecycle API:
----------------------
  session_service.create_session(app_name, user_id, state)   → Session
  session_service.get_session(app_name, user_id, session_id) → Session | None
  session_service.list_sessions(app_name, user_id)           → ListSessionsResponse
  session_service.delete_session(app_name, user_id, session_id) → None
  runner.run_async(user_id, session_id, content)             → async generator of Events
"""

import asyncio
import sys
from pathlib import Path

# Ensure the workspace root is on sys.path so `phase_2` is importable.
# Run this script from the workshop root: uv run python phase_2/persistence/run_with_persistence.py
_WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService, InMemorySessionService
from google.adk.memory import InMemoryMemoryService
from google.genai import types as genai_types

from lesson_2_sessions_memory.persistence.agent import root_agent


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
APP_NAME = "persistence"
USER_ID = "workshop_user_01"
SESSION_ID = "demo_session_fixed"  # fixed ID so second run resumes same session
DB_URL = "sqlite+aiosqlite:///./phase_2_sessions.db"


def make_user_message(text: str) -> genai_types.Content:
    return genai_types.Content(role="user", parts=[genai_types.Part(text=text)])


async def run_turn(runner: Runner, user_id: str, session_id: str, message: str) -> str:
    """Run one turn and return the agent's text response."""
    content = make_user_message(message)
    full_response = ""
    async for event in runner.run_async(
        user_id=user_id, session_id=session_id, new_message=content
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if hasattr(part, "text") and part.text:
                    full_response += part.text
    return full_response.strip()


async def print_state(session_service: DatabaseSessionService, label: str) -> None:
    """Print the current session state for inspection."""
    session = await session_service.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
    )
    if session is None:
        print(f"\n[{label}] Session does not exist yet.\n")
        return

    print(f"\n{'='*60}")
    print(f"[{label}] Session State:")
    print(f"  Session ID: {session.id}")
    state = session.state
    for key in sorted(state.keys()):
        if not key.startswith("temp:"):  # skip temp values (already expired)
            print(f"  {key!r}: {state[key]!r}")
    print(f"{'='*60}\n")


async def main():
    # ---------------------------------------------------------------------------
    # 1. Create the DatabaseSessionService
    #    The service automatically creates the schema on first use.
    # ---------------------------------------------------------------------------
    print(f"\nConnecting to SQLite database: {DB_URL}")
    session_service = DatabaseSessionService(db_url=DB_URL)
    memory_service = InMemoryMemoryService()

    # ---------------------------------------------------------------------------
    # 2. Create a Runner with the persistent session service
    # ---------------------------------------------------------------------------
    runner = Runner(
        agent=root_agent,
        app_name=APP_NAME,
        session_service=session_service,
        memory_service=memory_service,
    )

    # ---------------------------------------------------------------------------
    # 3. Create OR resume the session
    # ---------------------------------------------------------------------------
    existing_session = await session_service.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
    )

    if existing_session is None:
        print(f"No existing session found. Creating new session '{SESSION_ID}'...")
        await session_service.create_session(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=SESSION_ID,
            # Seed initial state — will be overwritten by before_agent_callback on first turn.
            state={"bootstrapped": True},
        )
        print("Session created. This is FIRST RUN.\n")
    else:
        user_name = existing_session.state.get("user:display_name", "Anonymous")
        note_count = existing_session.state.get("user:note_count", 0)
        print(f"Existing session found! Resuming for '{user_name}' ({note_count} notes ever).")
        print("This is a SUBSEQUENT RUN — state survived the process restart!\n")

    # Show state BEFORE any turns.
    await print_state(session_service, "Before Turns")

    # ---------------------------------------------------------------------------
    # 4. Run a short multi-turn conversation
    # ---------------------------------------------------------------------------
    print("--- Turn 1: Set display name ---")
    response = await run_turn(runner, USER_ID, SESSION_ID, "My name is Alice. Please remember it.")
    print(f"Agent: {response}\n")

    print("--- Turn 2: Create a note ---")
    response = await run_turn(runner, USER_ID, SESSION_ID,
                              "Create a note titled 'Workshop Key Insight' with content "
                              "'DatabaseSessionService persists state across restarts.'")
    print(f"Agent: {response}\n")

    print("--- Turn 3: Check persistence status ---")
    response = await run_turn(runner, USER_ID, SESSION_ID, "Show me the persistence status.")
    print(f"Agent: {response}\n")

    # Show state AFTER turns — user: and app: keys are now in the database.
    await print_state(session_service, "After Turns")

    # ---------------------------------------------------------------------------
    # 5. Demonstrate session listing
    # ---------------------------------------------------------------------------
    list_response = await session_service.list_sessions(app_name=APP_NAME, user_id=USER_ID)
    sessions = list_response.sessions if list_response else []
    print(f"\nAll sessions for user '{USER_ID}':")
    for s in sessions:
        print(f"  Session ID: {s.id} | Last updated: {s.last_update_time}")

    print("\n" + "="*60)
    print("Run this script again to see that state persists across restarts!")
    print("The user name, note count, and app counter will be restored from the DB.")
    print("="*60 + "\n")

    # ---------------------------------------------------------------------------
    # 6. Flush the session service (ensures all async writes are committed)
    # ---------------------------------------------------------------------------
    if hasattr(session_service, "flush"):
        await session_service.flush()


if __name__ == "__main__":
    asyncio.run(main())
