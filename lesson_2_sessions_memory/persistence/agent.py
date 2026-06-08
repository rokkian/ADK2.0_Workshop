"""
Phase 2 - Example 4: Persistence — DatabaseSessionService with SQLite
======================================================================

This module demonstrates how to replace the default in-memory session store
with a real database so that conversations survive process restarts.

InMemorySessionService vs. DatabaseSessionService:
---------------------------------------------------
  InMemorySessionService   — fast, zero config, data lost on restart.
  DatabaseSessionService   — SQLAlchemy-backed, any relational DB, persists forever.
  VertexAiSessionService   — fully managed by Google Cloud Agent Platform.

DatabaseSessionService constructor:
  DatabaseSessionService(db_url)
  db_url follows SQLAlchemy async format:
    SQLite  (dev)       → "sqlite+aiosqlite:///./sessions.db"
    PostgreSQL (prod)   → "postgresql+asyncpg://user:pass@host/db"
    MySQL   (prod)      → "mysql+aiomysql://user:pass@host/db"
  Requires the matching async driver installed (aiosqlite, asyncpg, aiomysql).

How the Runner Uses It:
-----------------------
  runner = Runner(
      agent=root_agent,
      app_name="persistence",
      session_service=DatabaseSessionService("sqlite+aiosqlite:///./sessions.db"),
      memory_service=InMemoryMemoryService(),   # swap for production
  )

  The runner creates the database schema automatically on first use.

State Persistence Semantics with DatabaseSessionService:
---------------------------------------------------------
  state["key"]          session-scoped → persisted for the life of this session.
  state["user:key"]     user-scoped → shared across ALL sessions of this user,
                         persisted in the database permanently.
  state["app:key"]      app-scoped → shared across ALL users, persisted.
  state["temp:key"]     invocation-only → never written to the DB.

This Example:
-------------
  Agent: A context-aware notes assistant that persists notes and user settings.
  See run_with_persistence.py for a full programmatic demonstration of creating
  sessions, resuming them after a "restart", and reading persisted state.
"""

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools import ToolContext
from google.genai import types as genai_types


# ---------------------------------------------------------------------------
# 1. State Initialization
# ---------------------------------------------------------------------------
async def initialize_user_state(callback_context: CallbackContext) -> genai_types.Content | None:
    """
    Safe-initializes state keys. With DatabaseSessionService, user: and app:
    keys written here will be read back correctly in future sessions.
    """
    state = callback_context.state

    # user: scoped — persists across ALL sessions for this user.
    if "user:display_name" not in state:
        state["user:display_name"] = "Anonymous"
    if "user:note_count" not in state:
        state["user:note_count"] = 0

    # app: scoped — global counter across all users.
    if "app:total_notes_created" not in state:
        state["app:total_notes_created"] = 0

    # session-scoped — fresh for every new conversation.
    if "session_notes" not in state:
        state["session_notes"] = []

    return None


# ---------------------------------------------------------------------------
# 2. Tool Functions
# ---------------------------------------------------------------------------

def create_note(title: str, content: str, tool_context: ToolContext) -> dict:
    """Create a new note and persist it in session and user state.

    Args:
        title: A short title for the note.
        content: The full text content of the note.
    """
    # Session-scoped: notes created in this conversation.
    session_notes = tool_context.state.get("session_notes", [])
    note = {"title": title, "content": content}
    session_notes.append(note)
    tool_context.state["session_notes"] = session_notes

    # Increment user-scoped counter — survives across sessions.
    tool_context.state["user:note_count"] = tool_context.state.get("user:note_count", 0) + 1

    # Increment app-scoped counter — survives across all users and restarts.
    tool_context.state["app:total_notes_created"] = (
        tool_context.state.get("app:total_notes_created", 0) + 1
    )

    return {
        "status": "created",
        "title": title,
        "user_total_notes": tool_context.state["user:note_count"],
        "app_total_notes": tool_context.state["app:total_notes_created"],
        "note": (
            "With DatabaseSessionService, user:note_count and app:total_notes_created "
            "survive process restarts. Session notes survive until this session is deleted."
        ),
    }


def list_session_notes(tool_context: ToolContext) -> dict:
    """List all notes created in the current session."""
    notes = tool_context.state.get("session_notes", [])
    return {
        "session_notes": notes,
        "count": len(notes),
        "user_total_notes_ever": tool_context.state.get("user:note_count", 0),
        "app_total_notes_ever": tool_context.state.get("app:total_notes_created", 0),
    }


def set_display_name(name: str, tool_context: ToolContext) -> dict:
    """Set your display name. Persisted across all your sessions.

    Args:
        name: The name to display in greetings.
    """
    tool_context.state["user:display_name"] = name.strip()
    return {
        "status": "updated",
        "name": name.strip(),
        "note": "This name will be remembered in all future sessions with DatabaseSessionService.",
    }


def get_persistence_status(tool_context: ToolContext) -> dict:
    """Show current persistence status — useful for explaining state scopes."""
    return {
        "user_display_name": tool_context.state.get("user:display_name", "Not set"),
        "user_note_count": tool_context.state.get("user:note_count", 0),
        "session_notes_this_session": len(tool_context.state.get("session_notes", [])),
        "app_total_notes_ever": tool_context.state.get("app:total_notes_created", 0),
        "explanation": {
            "session_notes": "Only in this conversation (session scope).",
            "user_note_count": "Across all your sessions (user: scope, requires DatabaseSessionService).",
            "app_total_notes_ever": "Across all users globally (app: scope, requires DatabaseSessionService).",
        },
    }


# ---------------------------------------------------------------------------
# 3. Agent Definition
# ---------------------------------------------------------------------------
root_agent = Agent(
    model="gemini-2.5-flash",
    name="notes_agent",
    description=(
        "A notes assistant that demonstrates DatabaseSessionService for "
        "true cross-session persistence of user: and app: scoped state."
    ),
    instruction="""
    You are a persistent notes assistant for {user:display_name}.

    Statistics:
      - Notes you have created in total: {user:note_count}
      - Notes created by all users (app-wide): {app:total_notes_created}
      - Notes in the current session: {session_notes}

    You can:
    - Create notes (title + content)
    - List notes from the current session
    - Show the full persistence status
    - Set the user's display name (persisted across sessions)

    When explaining how persistence works, describe the difference between
    session, user:, app:, and temp: state scopes clearly.
    Emphasise that `adk web` uses InMemorySessionService by default — to see
    true cross-session persistence, run the agent via run_with_persistence.py.
    """,
    tools=[create_note, list_session_notes, set_display_name, get_persistence_status],
    before_agent_callback=initialize_user_state,
    output_key="last_response",
)
