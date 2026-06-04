"""
ADK Workshop: Complex Travel Planner Agent
==========================================

This module implements a complex travel planner agent using modern Google ADK 2.0.
It implements a graph-based Workflow that coordinates multiple specialized agents
and integrates with a custom travel MCP server.

Architecture and ADK 2.0 Elements used:
--------------------------------------
1. Workflow (Graph Orchestration):
   Travel planning is non-linear and conditional. We use ADK 2.0 `Workflow` to define
   a Directed Acyclic Graph (DAG) with conditional branching.
   - START -> extract_preferences -> search_mcp_listings -> route_decision
   - If route_decision emits "book": route_decision -> mcp_booker -> itinerary_planner
   - If route_decision emits "itinerary": route_decision -> itinerary_planner

2. State Schema (TravelState):
   We define a global Pydantic state model (`TravelState`). Passing it to `state_schema`
   in the `Workflow` enables shared memory. Nodes read from and write to the state
   via `ctx.state`, allowing variables (like destination, dates, budget, booking status)
   to persist across executions.

3. FunctionNode (@node):
   We decorate python functions using `@node`. FunctionNodes allow running custom Python
   control logic (like state updates or branching assessments) directly in the graph.
   CRITICAL: Since these nodes dynamically schedule sub-nodes via `ctx.run_node()`, they
   MUST be configured with `rerun_on_resume=True` so that they can resume execution
   successfully when a sub-node completes.

4. Dynamic Node Execution (ctx.run_node):
   Rather than hardcoding static agent nodes, we use `await ctx.run_node(agent, prompt)`.
   This is a key ADK 2.0 feature allowing a parent FunctionNode to dynamically invoke
   specialist agents as "workers", passing precise inputs and collecting their outputs.

5. McpToolset:
   Integrates an external travel service (flight/hotel search and booking) exposing tools
   via the Model Context Protocol (MCP). The toolset connects to a stdio-based Python
   FastMCP server, dynamically importing its tools into our LLM agents' capabilities.

6. Event & EventActions(route=...):
   Used to return routing values from the `route_decision` node to guide the Workflow loop.
"""

from google.adk import Event
from google.adk.agents.llm_agent import Agent
from google.adk.agents.context import Context
from google.adk.events.event_actions import EventActions
from google.adk.workflow import Workflow, node
from google.adk.tools import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# 1. State Schema Definition
# ---------------------------------------------------------------------------
class TravelState(BaseModel):
    """Global state representing the travel booking and planning details."""
    destination: str = ""
    dates: str = ""
    budget: float = 0.0
    hotel_results: str = ""
    flight_results: str = ""
    selected_hotel_id: int = 0
    selected_flight_id: str = ""
    booking_status: str = "No booking confirmed."
    itinerary: str = ""

# ---------------------------------------------------------------------------
# 2. Toolset Configuration (MCP Server Connection)
# ---------------------------------------------------------------------------
# We connect to our custom travel MCP server running locally via stdio
travel_mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="python",
            args=["travel_planner/mcp_travel_server.py"]
        )
    )
)

# ---------------------------------------------------------------------------
# 3. Specialist Agents Definitions
# ---------------------------------------------------------------------------

# Structured parsing helper
class TravelPreferences(BaseModel):
    destination: str
    dates: str
    budget: float

preference_parser = Agent(
    model='gemini-2.5-flash',
    name='preference_parser',
    description='Extracts destination, dates, and budget from user prompt.',
    instruction='Extract the target destination, dates, and numeric budget from the user request.',
    output_schema=TravelPreferences
)

# Agent that uses MCP tools to search flights/hotels
mcp_search_agent = Agent(
    model='gemini-2.5-flash',
    name='mcp_search_agent',
    description='Searches flight and hotel options using MCP tools.',
    instruction='Search for available flights and accommodations using the provided tools, based on the destination and dates in the user request.',
    tools=[travel_mcp_toolset]
)

# Structured routing decision helper
class DecisionOutput(BaseModel):
    action: str  # Must be "book" or "itinerary"
    selected_hotel_id: int = 0
    selected_flight_id: str = ""
    reason: str

decision_agent = Agent(
    model='gemini-2.5-flash',
    name='decision_agent',
    description='Decides whether to book or plan itinerary based on search results and budget.',
    instruction=(
        'Review the budget and the search results. If there is a hotel and flight combination '
        'that fits within the budget, decide to "book", select the hotel ID (int) and flight ID (string), '
        'and state the reason. Otherwise, if it exceeds the budget, decide to do "itinerary" without booking.'
    ),
    output_schema=DecisionOutput
)

# Agent that uses MCP tools to confirm booking
mcp_booking_agent = Agent(
    model='gemini-2.5-flash',
    name='mcp_booking_agent',
    description='Confirms flight and hotel bookings using MCP tools.',
    instruction='Book the selected hotel and flight using the confirm_booking tool.',
    tools=[travel_mcp_toolset]
)

# Expert travel guide for planning itineraries
itinerary_agent = Agent(
    model='gemini-2.5-flash',
    name='itinerary_agent',
    description='Generates a complete holiday itinerary.',
    instruction='You are a travel guide. Create a day-by-day holiday itinerary based on the destination, dates, and booking status.',
)

# ---------------------------------------------------------------------------
# 4. Workflow Graph Node Implementations
# ---------------------------------------------------------------------------

def is_valid_input(val: str) -> bool:
    if not val:
        return False
    val_lower = val.strip().lower()
    return val_lower not in ["", "unknown", "none", "n/a", "not specified", "null", "undefined", "not provided"]

@node(name='extract_preferences', rerun_on_resume=True)
async def extract_preferences(node_input: str, ctx: Context) -> Event:
    """Node that extracts travel preferences from user prompt and writes them to state."""
    res = await ctx.run_node(preference_parser, node_input)
    
    # In ADK, run_node with output_schema may return a dict or a Pydantic object
    if isinstance(res, dict):
        destination = res.get('destination', '')
        dates = res.get('dates', '')
        try:
            budget = float(res.get('budget', 0.0) or 0)
        except (ValueError, TypeError):
            budget = 0.0
    else:
        destination = getattr(res, 'destination', '')
        dates = getattr(res, 'dates', '')
        try:
            budget = float(getattr(res, 'budget', 0.0) or 0)
        except (ValueError, TypeError):
            budget = 0.0

    destination = destination.strip() if destination else ""
    dates = dates.strip() if dates else ""

    # Save parameters in the global travel state
    ctx.state['destination'] = destination
    ctx.state['dates'] = dates
    ctx.state['budget'] = budget
    
    # Validate inputs
    missing = []
    if not is_valid_input(destination):
        missing.append("Destination")
    if not is_valid_input(dates):
        missing.append("Dates")
    if budget <= 0:
        missing.append("Budget")
        
    if missing:
        return Event(actions=EventActions(route='invalid'), output="Incomplete preferences")
        
    return Event(actions=EventActions(route='valid'), output=f"Extracted Preferences: Destination={destination}, Dates={dates}, Budget=${budget}")

@node(name='explain_agent')
async def explain_agent(ctx: Context) -> Event:
    """Node that explains what the travel agent can do when inputs are incomplete."""
    destination = ctx.state.get('destination', '')
    dates = ctx.state.get('dates', '')
    budget = ctx.state.get('budget', 0.0)
    
    missing = []
    if not is_valid_input(destination):
        missing.append("Destination")
    if not is_valid_input(dates):
        missing.append("Travel Dates")
    if budget <= 0:
        missing.append("Budget")
        
    missing_str = ", ".join(missing)
    
    explanation = (
        "Hello! I am your Travel Planner Agent. Here is what I can do for you:\n\n"
        "1. 🔍 **Search for flight and hotel options** matching your target destination and dates.\n"
        "2. 💳 **Book flights and hotels** automatically using MCP tools if they fit within your budget.\n"
        "3. 📅 **Generate a day-by-day travel itinerary** for your holiday.\n\n"
        "To start planning, please provide your travel details:\n"
        "- **Destination** (e.g., Paris, Tokyo)\n"
        "- **Travel Dates** (e.g., July 10-15)\n"
        "- **Budget** (e.g., $2000)\n\n"
        f"Currently, I am missing or couldn't parse: **{missing_str}**.\n\n"
        "Please provide all of these details (for example: *'Plan a trip to Paris from July 10-15 with a budget of $2000'*) so I can assist you!"
    )
    return Event(message=explanation)

@node(name='search_mcp_listings', rerun_on_resume=True)
async def search_mcp_listings(ctx: Context) -> str:
    """Node that queries flight/hotel availabilities using the MCP search agent."""
    destination = ctx.state.get('destination')
    dates = ctx.state.get('dates')
    
    prompt = f"Search flight and hotel options for {destination} during {dates}."
    res = await ctx.run_node(mcp_search_agent, prompt)
    
    # Save search results in the state
    ctx.state['hotel_results'] = res
    
    return res

@node(name='route_decision', rerun_on_resume=True)
async def route_decision(ctx: Context) -> Event:
    """Node that makes a routing decision based on the budget and available options."""
    budget = ctx.state.get('budget', 0.0)
    hotel_results = ctx.state.get('hotel_results', '')
    
    prompt = f"Review available options. My budget is ${budget}. Search results:\n{hotel_results}"
    res = await ctx.run_node(decision_agent, prompt)
    
    # In ADK, run_node with output_schema may return a dict or a Pydantic object
    if isinstance(res, dict):
        selected_hotel_id = int(res.get('selected_hotel_id', 0) or 0)
        selected_flight_id = res.get('selected_flight_id', '')
        action = res.get('action', 'itinerary')
        reason = res.get('reason', '')
    else:
        selected_hotel_id = int(getattr(res, 'selected_hotel_id', 0) or 0)
        selected_flight_id = getattr(res, 'selected_flight_id', '')
        action = getattr(res, 'action', 'itinerary')
        reason = getattr(res, 'reason', '')
        
    # Store decisions in the state
    ctx.state['selected_hotel_id'] = selected_hotel_id
    ctx.state['selected_flight_id'] = selected_flight_id
    
    # Return an Event to propagate the route key to the Workflow engine
    return Event(actions=EventActions(route=action), output=reason)

@node(name='mcp_booker', rerun_on_resume=True)
async def mcp_booker(ctx: Context) -> str:
    """Node that books the selected flights/hotels using the MCP booking agent."""
    hotel_id = ctx.state.get('selected_hotel_id')
    flight_id = ctx.state.get('selected_flight_id')
    
    prompt = f"Book hotel ID {hotel_id} and flight {flight_id} using the confirm_booking tool."
    res = await ctx.run_node(mcp_booking_agent, prompt)
    
    # Update booking status in the state
    ctx.state['booking_status'] = res
    
    return res

@node(name='itinerary_planner', rerun_on_resume=True)
async def itinerary_planner(ctx: Context) -> str:
    """Node that plans the daily itinerary based on booking outcomes."""
    destination = ctx.state.get('destination')
    dates = ctx.state.get('dates')
    booking_status = ctx.state.get('booking_status', 'No booking confirmed.')
    
    prompt = f"Plan a travel itinerary for {destination} on {dates}. Booking info: {booking_status}."
    res = await ctx.run_node(itinerary_agent, prompt)
    
    # Save final itinerary
    ctx.state['itinerary'] = res
    
    return res

# ---------------------------------------------------------------------------
# 5. Workflow Graph Assembly
# ---------------------------------------------------------------------------
root_agent = Workflow(
    name='root_agent',
    state_schema=TravelState,
    edges=[
        # Sequential initialization
        ('START', extract_preferences),
        (extract_preferences, {
            'valid': search_mcp_listings,
            'invalid': explain_agent
        }),
        (search_mcp_listings, route_decision),
        
        # Conditional branching based on route_decision output
        (route_decision, {
            'book': mcp_booker,
            'itinerary': itinerary_planner
        }),
        
        # Merge booking completion into itinerary generation
        (mcp_booker, itinerary_planner)
    ]
)
