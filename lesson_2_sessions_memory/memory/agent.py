"""
Phase 2 - Example 3: Memory — Cross-Session Knowledge with InMemoryMemoryService
==================================================================================

This module demonstrates how to give an agent long-term memory that spans
multiple conversation sessions. ADK separates two distinct memory layers:

  Session state (session.state)
    — A scratchpad scoped to ONE conversation.
    — Lost when the session ends (with InMemorySessionService).
    — Accessed via ToolContext.state or CallbackContext.state.

  Memory service (MemoryService)
    — A searchable knowledge store spanning MANY past conversations.
    — Survives across sessions (even InMemoryMemoryService survives within a
      server process lifetime, but is cleared on restart).
    — Populated by calling add_session_to_memory() at session end.
    — Queried by built-in tools or via tool_context.search_memory().

The Write–Read Memory Cycle:
-----------------------------
  1. User has a conversation → agent stores facts in session state.
  2. Session ends → after_agent_callback calls add_session_to_memory().
     The memory service indexes the session's events for future retrieval.
  3. New session begins → PreloadMemoryTool OR LoadMemoryTool queries the
     memory service and injects relevant past context into the agent's prompt.

Available Memory Tools:
------------------------
  PreloadMemoryTool  — searches memory AUTOMATICALLY at the start of each turn
                       and injects results into the system instruction. Zero
                       effort for the model, but always fetches (even when unneeded).
  LoadMemoryTool     — gives the model a MANUAL search tool. The LLM decides
                       when to call it. More efficient; requires model judgment.

This Example:
-------------
  Agent: a personal AI assistant that remembers facts you tell it.
  Memory tool: PreloadMemoryTool (automatic, best for demos).
  Storage: InMemoryMemoryService (no setup required, resets on restart).
  Memory write: after_agent_callback → add_session_to_memory().

NOTE on InMemoryMemoryService vs. production:
  InMemoryMemoryService uses keyword extraction — it will recall recent facts
  within the same server process. For semantic search and true persistence use
  VertexAiMemoryBankService or DatabaseMemoryService (see persistence example).
"""

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.adk.tools.load_memory_tool import LoadMemoryTool
from google.genai import types as genai_types


# ---------------------------------------------------------------------------
# 1. Memory Write — after_agent_callback
# ---------------------------------------------------------------------------
async def save_session_to_memory(callback_context: CallbackContext) -> genai_types.Content | None:
    """
    Runs after EVERY agent turn. Sends the current session's events to the
    memory service so they can be recalled in future sessions.

    The memory service is wired into the runner. With `adk web` the dev server
    uses InMemoryRunner which already includes an InMemoryMemoryService.
    With a custom Runner you supply whichever MemoryService you choose.

    IMPORTANT: add_session_to_memory() raises ValueError if no memory service
    is configured. Always guard with a try/except in production.
    """
    try:
        # This is the key API: stores the session's event history in the
        # memory service so it can be retrieved in future sessions.
        await callback_context.add_session_to_memory()
    except ValueError:
        # No memory service configured — safe to skip in dev environments.
        pass

    return None  # do not alter the agent's response


# ---------------------------------------------------------------------------
# 2. Tool Functions — Storing Explicit Facts
# ---------------------------------------------------------------------------

def remember_fact(fact: str, category: str, tool_context: ToolContext) -> dict:
    """Store an important fact about the user for future recall.

    Call this when the user explicitly asks to remember something, or when
    the conversation reveals a clearly important personal detail.

    Args:
        fact: The fact to remember (e.g., 'User is allergic to peanuts').
        category: A label for the fact (e.g., 'health', 'preference', 'contact').
    """
    # Write the fact to session state so it is part of this session's events.
    # When add_session_to_memory() runs after this turn, the memory service
    # will index these events — including this state write.
    facts = tool_context.state.get("remembered_facts", [])
    entry = {"category": category, "fact": fact}
    facts.append(entry)
    tool_context.state["remembered_facts"] = facts

    return {
        "status": "remembered",
        "fact": fact,
        "category": category,
        "total_facts_this_session": len(facts),
        "note": "This fact will be persisted to memory at the end of this turn.",
    }


def search_my_memory(query: str, tool_context: ToolContext) -> dict:
    """Manually search long-term memory for facts matching a query.

    Use this when the user asks about something that might have been mentioned
    in a previous conversation, not just the current session.

    Args:
        query: Natural language description of what to look for.
    """
    import asyncio

    async def _search():
        results = await tool_context.search_memory(query)
        return results

    # ToolContext.search_memory is async; we bridge it for the sync tool signature.
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Inside an async context — use a nested run via a thread.
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, tool_context.search_memory(query))
                memories = future.result()
        else:
            memories = loop.run_until_complete(tool_context.search_memory(query))
    except Exception as e:
        return {"status": "error", "message": str(e)}

    if not memories or not memories.memories:
        return {"status": "no_results", "query": query, "memories": []}

    results = [
        {
            "session_id": entry.session_id,
            "content": str(entry.content)[:300],  # truncate for display
        }
        for entry in memories.memories
    ]
    return {"status": "success", "query": query, "results": results}


def list_session_facts(tool_context: ToolContext) -> dict:
    """List all facts explicitly remembered during the current session."""
    facts = tool_context.state.get("remembered_facts", [])
    return {
        "session_facts": facts,
        "count": len(facts),
        "note": (
            "These are facts from THIS session only. "
            "Memories from past sessions are automatically loaded by PreloadMemoryTool."
        ),
    }


# ---------------------------------------------------------------------------
# 3. Agent Assembly — Memory Tools + Callback
# ---------------------------------------------------------------------------
root_agent = Agent(
    model="gemini-2.5-flash",
    name="personal_assistant_agent",
    description=(
        "A personal AI assistant that remembers facts across conversations "
        "using ADK's memory service."
    ),
    instruction="""
    You are a thoughtful personal AI assistant with long-term memory.

    At the start of each turn, past conversation summaries are automatically
    loaded via PreloadMemoryTool and injected into your context.

    Your behaviour:
    1. Greet the user by name if you remember it from memory.
    2. Proactively reference facts from past conversations when relevant.
    3. Call remember_fact() when the user explicitly asks you to remember
       something, or when they share clearly important personal information
       (name, dietary restrictions, preferences, important dates, etc.).
    4. Call search_my_memory() when the user asks about something that
       might be in a past conversation and PreloadMemoryTool did not surface it.
    5. Call list_session_facts() to show what was remembered this session.

    Be warm, proactive about using memory, and always acknowledge when you
    are recalling something from a past conversation.
    """,
    tools=[
        # PreloadMemoryTool runs automatically at the start of every turn.
        # It queries the memory service with the conversation context and injects
        # matching past memories directly into the system instruction.
        # The model does NOT need to call it — it is transparent.
        PreloadMemoryTool(),

        # LoadMemoryTool gives the model a manual search capability.
        # Use this when PreloadMemoryTool might miss specific facts.
        # The model will call this tool when it decides it needs to search.
        LoadMemoryTool(),

        # Custom tools for explicit fact management.
        remember_fact,
        search_my_memory,
        list_session_facts,
    ],
    # after_agent_callback: at the end of every turn, index this session in memory.
    # This is the mechanism that makes facts available in future sessions.
    after_agent_callback=save_session_to_memory,
)
