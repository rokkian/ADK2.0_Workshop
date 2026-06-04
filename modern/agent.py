"""
ADK Workshop Step 3: Modern ADK 2.0 Features (Graph Workflows)
=============================================================

This module demonstrates the new graph-based orchestration engine introduced in ADK 2.0.
Specifically, it showcases:
1. Workflow: A graph-based execution container defining edges, transitions, and execution flow.
2. FunctionNode (@node): Decorating standard python functions to behave as node executors in the graph.
3. Event & EventActions: Conveying custom actions, such as graph-based routing, back to the orchestrator.

Why these elements were used:
-----------------------------
- `Workflow` replaces older, less flexible orchestration loops by compiling a directed graph
  of execution. The `edges` parameter maps how data flows:
  * `('START', check_query_route)` starts execution at our routing node.
  * `(check_query_route, {'math': math_specialist, 'general': general_assistant})` represents a
    conditional routing fork, matching the router's emitted route against the dictionary keys.
- `@node` is a decorator that converts a standard Python function into a `FunctionNode`.
  This allows arbitrary Python logic (like string matching or regex) to execute inside the graph.
- `Event` and `EventActions(route=...)` are used to control the graph state. By returning an `Event`
  containing `EventActions(route=target_route)`, the FunctionNode tells the `Workflow` loop
  which path of the conditional edge map to follow.
"""

from google.adk import Event
from google.adk.agents.llm_agent import Agent
from google.adk.events.event_actions import EventActions
from google.adk.workflow import Workflow, node

# Specialist Agent for Math Tasks
math_specialist = Agent(
    model="gemini-2.5-flash",
    name="math_specialist",
    description="A specialist agent that excels at solving mathematics problems.",
    instruction="You are an expert mathematician. Solve the mathematics problem step-by-step.",
)

# General Assistant for Standard Chats
general_assistant = Agent(
    model="gemini-2.5-flash",
    name="general_assistant",
    description="A general helpful assistant for standard conversations.",
    instruction="You are a helpful assistant. Reply to the user nicely.",
)


@node(name="router_node")
def check_query_route(node_input: str) -> Event:
    """Analyze user input and route to math or general agent by yielding an Event.

    Args:
        node_input: The user query string.
    """
    query = node_input.lower()
    if any(
        keyword in query
        for keyword in [
            "math",
            "calculate",
            "solve",
            "equation",
            "sum",
            "plus",
            "minus",
            "multiply",
            "divide",
            "calculator",
        ]
    ):
        target_route = "math"
    else:
        target_route = "general"

    # Return an Event containing the selected route in actions to guide the Workflow loop
    return Event(actions=EventActions(route=target_route))


# Assemble the graph routing workflow
root_agent = Workflow(
    name="root_agent",
    edges=[
        ("START", check_query_route),
        (check_query_route, {"math": math_specialist, "general": general_assistant}),
    ],
)
