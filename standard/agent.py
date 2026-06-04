"""
ADK Workshop Step 2: Standard Elements & Tools
==============================================

This module demonstrates the use of standard Google ADK (Agent Development Kit) elements.
Specifically, it showcases:
1. Agent: The core unit of intelligence representing an LLM-backed agent.
2. Custom Tools: Passing standard Python functions directly to the agent.
3. ToolContext: Accessing session state, user ID, and execution variables at runtime.

Why these elements were used:
-----------------------------
- `Agent` constructor is used to initialize the agent. By passing `model='gemini-2.5-flash'`
  and a clear list of `tools`, we give the LLM reasoning loop the capability to execute
  external functions when it determines it needs to.
- `roll_dice` is a simple Python function that utilizes standard type hints and a docstring.
  ADK automatically extracts this metadata to construct the JSON schema for Gemini's function call declaration.
- `get_session_details` demonstrates `ToolContext`. When a parameter named `context` (or type-annotated
  with `ToolContext`) is declared, the ADK automatically injects this context at runtime, while
  hiding it from the JSON schema sent to the LLM (as the LLM does not need to supply this parameter).
  This allows retrieving runtime metadata (like `user_id` and `run_id`) securely and dynamically.
"""

import random
from google.adk.agents.llm_agent import Agent
from google.adk.tools import ToolContext


def roll_dice(num_dice: int, sides: int = 6) -> int:
    """Roll one or more dice with a given number of sides.

    Args:
        num_dice: The number of dice to roll.
        sides: The number of sides on each die.
    """
    return sum(random.randint(1, sides) for _ in range(num_dice))


def get_session_details(context: ToolContext) -> str:
    """Get details of the current execution session.

    Returns:
        A string describing the session and run identifier.
    """
    return f"Running in session {context.run_id} for user {context.user_id}."


# Configure standard_agent with our custom tools
root_agent = Agent(
    model="gemini-2.5-flash",
    name="standard_agent",
    description="An agent with standard custom tools.",
    instruction="""
    You have custom tools to roll dice and retrieve session details.
    Use them when appropriate to answer the user.
    """,
    tools=[roll_dice, get_session_details],
)
