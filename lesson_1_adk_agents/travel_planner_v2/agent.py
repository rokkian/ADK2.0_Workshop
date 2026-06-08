"""
ADK Workshop Step 6: Advanced Multi-Agent Travel Planner v2
===========================================================

This module implements an ambitious travel planner agent showcasing:
1. Graph-based Workflow Orchestration (Workflow with complex conditional routing).
2. Shared State Memory using Pydantic schema validation.
3. Multi-Agent Collaboration: Supervisor orchestrating multiple worker agents dynamically.
4. Multiple external MCP servers: Travel MCP, Airbnb MCP, TripAdvisor MCP, Google Flights MCP, and Wikipedia MCP.
5. Remote A2A Agent Integration: Queries currency, weather, loyalty, and payment escrow A2A agents.
6. Agentic Payments Protocol (x402/MPP): Implements client-to-agent fee challenges and escrow payment tokens.
"""

import os
import copy
import json
import logging
from pathlib import Path
from typing import Any
from dotenv import load_dotenv

# Load environment variables from the root .env file if it exists
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path, override=True)

# Force Gemini Developer API (using API Key) instead of Vertex AI
os.environ['GOOGLE_GENAI_USE_VERTEXAI'] = '0'
if 'GOOGLE_API_KEY' in os.environ:
    os.environ['GEMINI_API_KEY'] = os.environ['GOOGLE_API_KEY']

from google.adk import Event
from google.adk.agents.llm_agent import Agent
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.agents.context import Context
from google.adk.events.event_actions import EventActions
from google.adk.workflow import Workflow, node
from google.adk.tools import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 1. State Schema Definition
# ---------------------------------------------------------------------------
class TravelState(BaseModel):
    """Global state representing the travel planning, booking, and payment ledger."""
    destination: str = ""
    dates: str = ""
    budget: float = 0.0
    currency: str = "USD"
    converted_budget: float = 0.0  # Budget converted to USD via A2A Currency Agent
    weather_forecast: str = ""     # Weather forecast details retrieved via A2A Weather Agent
    loyalty_discount: float = 0.0  # Discount rate (e.g. 0.15 for 15% off) via A2A Loyalty Agent
    hotel_results: str = ""
    flight_results: str = ""
    selected_hotel_id: int = 0
    selected_flight_id: str = ""
    booking_status: str = "No booking confirmed."
    itinerary: str = ""
    
    # Agentic Payments Wallet & Ledger details
    agent_wallet_balance: float = 10.00  # Initial wallet balance (USD) for machine payments
    payment_ledger: list[dict] = []
    payment_status: str = "UNPAID"

# ---------------------------------------------------------------------------
# 2. Toolsets and MCP Servers Configurations
# ---------------------------------------------------------------------------

# Travel MCP Server Configuration (custom local Python server)
travel_mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="python",
            args=["travel_planner_v2/mcp_travel_server.py"]
        )
    )
)

# Airbnb MCP Server Configuration (Local Python FastMCP server)
airbnb_mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="python",
            args=["travel_planner_v2/mcp_airbnb_server.py"]
        )
    )
)

# TripAdvisor MCP Server Configuration (Python-based, via uvx)
tripadvisor_mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="uvx",
            args=["--from", "git+https://github.com/pab1it0/tripadvisor-mcp", "tripadvisor-mcp"],
            env={
                "TRIPADVISOR_API_KEY": os.environ.get("TRIPADVISOR_API_KEY", "MOCK_TRIPADVISOR_KEY"),
                "PATH": os.environ.get("PATH", "")
            }
        )
    )
)

# Google Flights MCP Server Configuration (Local Python FastMCP server)
flights_mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="python",
            args=["travel_planner_v2/mcp_flights_server.py"]
        )
    )
)

# Wikipedia MCP Server Configuration (Local Python FastMCP server)
wikipedia_mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="python",
            args=["travel_planner_v2/mcp_wikipedia_server.py"]
        )
    )
)

# ---------------------------------------------------------------------------
# 3. Remote A2A Agents Configurations
# ---------------------------------------------------------------------------
currency_a2a_agent = RemoteA2aAgent(
    name="currency_converter",
    agent_card="http://localhost:8006/.well-known/agent-card.json"
)

weather_a2a_agent = RemoteA2aAgent(
    name="weather_forecaster",
    agent_card="http://localhost:8007/.well-known/agent-card.json"
)

escrow_a2a_agent = RemoteA2aAgent(
    name="payment_escrow",
    agent_card="http://localhost:8008/.well-known/agent-card.json"
)

loyalty_a2a_agent = RemoteA2aAgent(
    name="loyalty_discounts",
    agent_card="http://localhost:8009/.well-known/agent-card.json"
)

# ---------------------------------------------------------------------------
# 4. Helper functions for x402 / MPP Agentic Payments Protocol
# ---------------------------------------------------------------------------
def safe_get(obj, key, default=None):
    if obj is None:
        return default
    # 1. Handle ADK Event objects containing output
    if hasattr(obj, "output") and obj.output:
        val = safe_get(obj.output, key, None)
        if val is not None:
            return val
    # 2. Handle standard dictionaries
    if isinstance(obj, dict):
        return obj.get(key, default)
    # 3. Handle JSON strings
    if isinstance(obj, str):
        try:
            data = json.loads(obj)
            if isinstance(data, dict):
                return data.get(key, default)
        except json.JSONDecodeError:
            pass
    # 4. Handle Pydantic models (check dict method)
    if hasattr(obj, "dict"):
        try:
            val = obj.dict().get(key, None)
            if val is not None:
                return val
        except Exception:
            pass
    # 5. General fallback to attribute retrieval
    return getattr(obj, key, default)

async def run_remote_agent(ctx: Context, remote_agent: RemoteA2aAgent, payload: str) -> Any:
    """Runs a RemoteA2aAgent and extracts its response event payload."""
    await ctx.run_node(remote_agent, payload)
    for event in reversed(ctx.session.events):
        if event.author == remote_agent.name:
            if event.content and event.content.parts:
                text = "".join(part.text for part in event.content.parts if part.text)
                if text:
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        return text
    return None

async def run_a2a_with_payment(ctx: Context, remote_agent: RemoteA2aAgent, query_str: str, agent_name: str, fallback_func) -> Any:
    """Helper to orchestrate x402 / MPP Agentic Payments protocol with a remote agent.
    If the remote agent returns 402_PAYMENT_REQUIRED, this function calls the Escrow Agent
    to authorize a transfer, get a payment proof token, and retry the request.
    """
    initial_payload = json.dumps({"query": query_str})
    try:
        logger.info(f"Querying remote A2A agent {agent_name} with: {initial_payload}")
        res = await run_remote_agent(ctx, remote_agent, initial_payload)
        logger.info(f"Received response from {agent_name}: {res}")
    except Exception as e:
        logger.warning(f"Failed to query {agent_name} directly: {e}. Falling back.")
        return fallback_func()
        
    status = safe_get(res, "status")
    logger.info(f"Extracted status for {agent_name}: {status}")
    
    if status == "402_PAYMENT_REQUIRED":
        fee = float(safe_get(res, "fee_usd", 0.0) or 0.0)
        dest_wallet = safe_get(res, "destination_wallet", "")
        challenge = safe_get(res, "challenge", "")
        
        logger.info(f"[x402] Payment Challenge Received: {fee} USD needed for {agent_name}. Challenge: {challenge}")
        
        # Log challenge in ledger (status: PENDING)
        ledger = ctx.state.get('payment_ledger', [])
        tx_challenge = {
            "agent_name": agent_name,
            "action": f"x402 Challenge: {challenge}",
            "cost_usd": fee,
            "status": "PENDING"
        }
        ledger.append(tx_challenge)
        ctx.state['payment_ledger'] = ledger
        
        # Invoke the Escrow Agent to make the payment
        escrow_payload = json.dumps({
            "action": "transfer",
            "from_wallet": "client_supervisor_wallet",
            "to_wallet": dest_wallet,
            "amount_usd": fee,
            "challenge": challenge
        })
        
        logger.info(f"Invoking Escrow Agent to pay {fee} USD for {agent_name}...")
        try:
            escrow_res = await run_remote_agent(ctx, escrow_a2a_agent, escrow_payload)
            escrow_status = safe_get(escrow_res, "status")
            logger.info(f"Escrow Agent response: {escrow_res} (Status: {escrow_status})")
        except Exception as e:
            logger.warning(f"Failed to query Escrow Agent: {e}")
            tx_challenge["status"] = "FAILED (Escrow Offline)"
            ctx.state['payment_ledger'] = ledger
            return fallback_func()
            
        if escrow_status == "SUCCESS":
            proof = safe_get(escrow_res, "payment_proof")
            new_bal = safe_get(escrow_res, "remaining_balance", 10.0)
            
            logger.info(f"Payment successful. Proof: {proof}. New Wallet Balance: {new_bal}")
            
            # Update state with proof and wallet balance
            ctx.state['agent_wallet_balance'] = round(new_bal, 4)
            tx_challenge["status"] = "SUCCESS"
            tx_challenge["action"] = f"Paid fee for {agent_name} (Proof: {proof[:15]}...)"
            ctx.state['payment_ledger'] = ledger
            
            # Retry the request with the payment proof
            retry_payload = json.dumps({
                "query": query_str,
                "payment_proof": proof
            })
            
            logger.info(f"Retrying A2A agent {agent_name} with payment proof...")
            try:
                final_res = await run_remote_agent(ctx, remote_agent, retry_payload)
                logger.info(f"Final A2A response from {agent_name}: {final_res}")
                return final_res
            except Exception as e:
                logger.warning(f"Failed to query {agent_name} after payment: {e}")
                return fallback_func()
        else:
            msg = safe_get(escrow_res, "message", "Insufficient Funds")
            tx_challenge["status"] = f"FAILED ({msg})"
            ctx.state['payment_ledger'] = ledger
            logger.warning(f"Payment failed for {agent_name}: {msg}")
            return fallback_func()
            
    return res

def charge_agent_payment(ctx: Context, agent_name: str, action: str, cost: float) -> bool:
    """Simulates an Agentic Payment protocol (like x402 / MPP) inside the workflow.
    Deducts the cost from the agent's wallet and logs it in the transaction ledger.
    """
    balance = ctx.state.get('agent_wallet_balance', 10.00)
    ledger = ctx.state.get('payment_ledger', [])
    
    status = "SUCCESS" if balance >= cost else "FAILED_INSUFFICIENT_FUNDS"
    new_balance = balance - cost if balance >= cost else balance
    
    ctx.state['agent_wallet_balance'] = round(new_balance, 4)
    
    transaction = {
        "agent_name": agent_name,
        "action": action,
        "cost_usd": cost,
        "status": status
    }
    ledger.append(transaction)
    ctx.state['payment_ledger'] = ledger
    
    return status == "SUCCESS"

# ---------------------------------------------------------------------------
# 5. Specialist Agents Definitions
# ---------------------------------------------------------------------------
class TravelPreferences(BaseModel):
    destination: str = Field(description="The target destination city or airport code.")
    dates: str = Field(description="The travel check-in and check-out dates.")
    budget: float = Field(description="The numeric budget amount.")
    currency: str = Field(default="USD", description="The currency code (e.g. USD, EUR, JPY, GBP).")

preference_parser = Agent(
    model='gemini-2.5-flash',
    name='preference_parser',
    description='Extracts destination, dates, budget, and currency from user request.',
    instruction='Extract the target destination, dates, numeric budget, and currency code from the user request.',
    output_schema=TravelPreferences
)

# Multi-Tool Search Agent
mcp_search_agent = Agent(
    model='gemini-2.5-flash',
    name='mcp_search_agent',
    description='Queries accommodations, flights, attractions, and cultural background info using multiple MCP servers.',
    instruction=(
        'Search for available accommodations, flights, and travel/cultural info using the provided MCP tools. '
        'Use the wikipedia tool to query local history/facts about the destination. '
        'If the tools fail or are offline, generate realistic mock suggestions for accommodations, '
        'Airbnb listings, flights, and TripAdvisor recommendations, clearly stating it is a simulation.'
    ),
    tools=[travel_mcp_toolset, airbnb_mcp_toolset, tripadvisor_mcp_toolset, flights_mcp_toolset, wikipedia_mcp_toolset]
)

class DecisionOutput(BaseModel):
    action: str  # Must be "book" or "itinerary"
    selected_hotel_id: int = 0
    selected_flight_id: str = ""
    reason: str

decision_agent = Agent(
    model='gemini-2.5-flash',
    name='decision_agent',
    description='Reviews budget and listings to make routing decisions.',
    instruction=(
        'Review the budget (in USD) and search results. If there is a hotel and flight combination '
        'that fits within the budget, decide to "book", select the hotel ID (int) and flight ID (string), '
        'and state the reason. Otherwise, decide to do "itinerary" without booking.'
    ),
    output_schema=DecisionOutput
)

mcp_booking_agent = Agent(
    model='gemini-2.5-flash',
    name='mcp_booking_agent',
    description='Confirms flight and hotel bookings using MCP booking tools.',
    instruction='Book the selected hotel and flight using the confirm_booking tool.',
    tools=[travel_mcp_toolset]
)

itinerary_agent = Agent(
    model='gemini-2.5-flash',
    name='itinerary_agent',
    description='Generates a complete travel guide itinerary.',
    instruction='You are a travel guide. Create a detailed day-by-day holiday itinerary based on the destination, dates, weather details, and booking status.',
)

# ---------------------------------------------------------------------------
# 6. Workflow Graph Node Implementations
# ---------------------------------------------------------------------------
def is_valid_input(val: str) -> bool:
    if not val:
        return False
    val_lower = val.strip().lower()
    return val_lower not in ["", "unknown", "none", "n/a", "not specified", "null", "undefined", "not provided"]

@node(name='extract_preferences', rerun_on_resume=True)
async def extract_preferences(node_input: str, ctx: Context) -> Event:
    """Node that extracts travel preferences from user prompt and writes them to state."""
    charge_agent_payment(ctx, "preference_parser", "Parse user preferences", 0.05)
    
    res = await ctx.run_node(preference_parser, node_input)
    
    destination = safe_get(res, 'destination', '')
    dates = safe_get(res, 'dates', '')
    currency = safe_get(res, 'currency', 'USD')
    try:
        budget = float(safe_get(res, 'budget', 0.0) or 0)
    except (ValueError, TypeError):
        budget = 0.0

    destination = destination.strip() if destination else ""
    dates = dates.strip() if dates else ""
    currency = currency.strip().upper() if currency else "USD"

    # Save parameters in the global travel state
    ctx.state['destination'] = destination
    ctx.state['dates'] = dates
    ctx.state['budget'] = budget
    ctx.state['currency'] = currency
    ctx.state['converted_budget'] = budget

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
        
    return Event(actions=EventActions(route='valid'), output=f"Extracted Preferences: Destination={destination}, Dates={dates}, Budget={budget} {currency}")

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
    
    # Format the Agentic Payment Ledger
    ledger = ctx.state.get('payment_ledger', [])
    balance = ctx.state.get('agent_wallet_balance', 10.00)
    
    ledger_str = "\n\n### 💳 Agentic Payments Ledger (x402 / MPP Protocol)\n"
    ledger_str += "| Agent Name | Action | Cost (USD) | Status |\n"
    ledger_str += "| :--- | :--- | :--- | :--- |\n"
    for tx in ledger:
        status_icon = "🟢 SUCCESS" if tx.get('status') == "SUCCESS" else "🔴 FAILED"
        ledger_str += f"| `{tx.get('agent_name')}` | {tx.get('action')} | ${tx.get('cost_usd', 0.0):.4f} | {status_icon} |\n"
        
    ledger_str += f"\n**Remaining Agent Wallet Balance**: `${balance:.4f} USD`\n"
    
    explanation = (
        "Hello! I am your Travel Planner Agent. Here is what I can do for you:\n\n"
        "1. 🔍 **Search for flight and hotel options** matching your destination across 5 external MCP servers.\n"
        "2. 🌤️ **Fetch weather forecasts & cultural history** via dedicated A2A Agents.\n"
        "3. 💳 **Book flights and hotels** automatically using machine-to-machine wallet operations (x402 protocol).\n"
        "4. 📅 **Generate a day-by-day travel itinerary** for your holiday.\n\n"
        "To start planning, please provide your travel details:\n"
        "- **Destination** (e.g., Paris, Tokyo)\n"
        "- **Travel Dates** (e.g., July 10-15)\n"
        "- **Budget** (e.g., $2000 or 1500 EUR)\n\n"
        f"Currently, I am missing or couldn't parse: **{missing_str}**.\n\n"
        "Please provide all of these details (for example: *'Plan a trip to Paris from July 10-15 with a budget of $2000'*) so I can assist you!"
        + ledger_str
    )
    return Event(message=explanation)

@node(name='currency_conversion', rerun_on_resume=True)
async def currency_conversion(ctx: Context) -> Event:
    """Invokes Remote A2A Currency Converter Agent to convert the budget to USD if needed."""
    budget = ctx.state.get('budget', 0.0)
    currency = ctx.state.get('currency', 'USD')
    
    if currency == 'USD':
        ctx.state['converted_budget'] = budget
        return Event(actions=EventActions(route='success'), output="Budget is already in USD.")
        
    def local_fallback():
        rates = {'EUR': 1.08, 'JPY': 0.0064, 'GBP': 1.27}
        rate = rates.get(currency, 1.0)
        converted = budget * rate
        ctx.state['converted_budget'] = converted
        ctx.state['budget'] = converted
        ctx.state['currency'] = 'USD'
        return Event(actions=EventActions(route='success'), output=f"Fallback Conversion: {budget} {currency} -> {converted} USD (A2A Offline)")

    query = f"Convert {budget} {currency} to USD."
    res = await run_a2a_with_payment(ctx, currency_a2a_agent, query, "currency_converter", local_fallback)
    
    if isinstance(res, Event):
        return res
        
    status = safe_get(res, "status")
    if status == "SUCCESS":
        converted = float(safe_get(res, "converted_amount", budget) or budget)
        rate = float(safe_get(res, "rate", 1.0) or 1.0)
        ctx.state['converted_budget'] = converted
        ctx.state['budget'] = converted
        ctx.state['currency'] = 'USD'
        return Event(actions=EventActions(route='success'), output=f"A2A Conversion: {budget} {currency} -> {converted} USD at rate {rate}")
        
    return local_fallback()

@node(name='fetch_weather', rerun_on_resume=True)
async def fetch_weather(ctx: Context) -> str:
    """Queries destination weather forecast via the Weather Forecaster A2A agent."""
    destination = ctx.state.get('destination')
    dates = ctx.state.get('dates')
    
    def local_fallback():
        forecast = f"Simulated Weather for {destination} ({dates}): Warm and sunny, average 26°C. Clear skies. Pack light clothes and sunscreen."
        ctx.state['weather_forecast'] = forecast
        return forecast

    query = f"Forecast for {destination} during {dates}."
    res = await run_a2a_with_payment(ctx, weather_a2a_agent, query, "weather_forecaster", local_fallback)
    
    if isinstance(res, str) and not res.startswith("{"):
        return res
        
    status = safe_get(res, "status")
    if status == "SUCCESS":
        forecast = safe_get(res, "forecast", "")
        ctx.state['weather_forecast'] = forecast
        return forecast
        
    return local_fallback()

@node(name='search_listings', rerun_on_resume=True)
async def search_listings(ctx: Context) -> str:
    """Queries flight/hotel/Airbnb/Wikipedia options using the multi-tool MCP search agent."""
    destination = ctx.state.get('destination')
    dates = ctx.state.get('dates')
    
    charge_agent_payment(ctx, "mcp_search_agent", f"Query listings for {destination} via MCP", 0.15)
    
    prompt = f"Search flight, hotel, and Airbnb options for {destination} during {dates}. Also search Wikipedia details for {destination}."
    res = await ctx.run_node(mcp_search_agent, prompt)
    
    ctx.state['hotel_results'] = res
    
    return res

@node(name='route_decision', rerun_on_resume=True)
async def route_decision(ctx: Context) -> Event:
    """Formulates a decision based on budget and search results."""
    budget = ctx.state.get('converted_budget', 0.0)
    hotel_results = ctx.state.get('hotel_results', '')
    
    charge_agent_payment(ctx, "decision_agent", "Evaluate listings against budget", 0.05)
    
    prompt = f"Review available options. My budget is ${budget}. Search results:\n{hotel_results}"
    res = await ctx.run_node(decision_agent, prompt)
    
    selected_hotel_id = int(safe_get(res, 'selected_hotel_id', 0) or 0)
    selected_flight_id = safe_get(res, 'selected_flight_id', '')
    action = safe_get(res, 'action', 'itinerary')
    reason = safe_get(res, 'reason', '')
        
    ctx.state['selected_hotel_id'] = selected_hotel_id
    ctx.state['selected_flight_id'] = selected_flight_id
    
    return Event(actions=EventActions(route=action), output=reason)

@node(name='apply_loyalty_discount', rerun_on_resume=True)
async def apply_loyalty_discount(ctx: Context) -> str:
    """Queries Loyalty Discounts A2A agent to get traveler booking discounts."""
    destination = ctx.state.get('destination')
    hotel_id = ctx.state.get('selected_hotel_id')
    
    def local_fallback():
        ctx.state['loyalty_discount'] = 0.05
        return "Applied 5% fallback loyalty discount."
        
    query = f"Get hotel discount for VIP status at Hotel ID {hotel_id} in {destination}."
    res = await run_a2a_with_payment(ctx, loyalty_a2a_agent, query, "loyalty_discounts", local_fallback)
    
    if isinstance(res, str) and not res.startswith("{"):
        return res
        
    status = safe_get(res, "status")
    if status == "SUCCESS":
        discount = float(safe_get(res, "discount_rate", 0.05) or 0.05)
        ctx.state['loyalty_discount'] = discount
        msg = safe_get(res, "message", "Applied loyalty discount.")
        return f"Loyalty discount of {discount*100}% applied: {msg}"
        
    return local_fallback()

@node(name='validate_payment', rerun_on_resume=True)
async def validate_payment(ctx: Context) -> Event:
    """Validates the booking transaction against the budget and ledger rules."""
    budget = ctx.state.get('converted_budget', 0.0)
    hotel_id = ctx.state.get('selected_hotel_id', 0)
    flight_id = ctx.state.get('selected_flight_id', "")
    loyalty_discount = ctx.state.get('loyalty_discount', 0.0)
    
    # Calculate simulated booking cost
    flight_cost = 350.0 if "101" in str(flight_id) else (220.0 if "202" in str(flight_id) else 300.0)
    hotel_rate = 150.0 if hotel_id == 501 else (80.0 if hotel_id == 502 else (30.0 if hotel_id == 503 else 100.0))
    raw_booking_cost = flight_cost + (hotel_rate * 7) # assuming 7 nights
    
    # Apply loyalty discount
    booking_cost = round(raw_booking_cost * (1.0 - loyalty_discount), 2)
    
    if booking_cost <= budget:
        ctx.state['payment_status'] = "PAID"
        # Log external booking cost (charged to client's account, NOT agent's wallet)
        ledger = ctx.state.get('payment_ledger', [])
        ledger.append({
            "agent_name": "booking_gateway",
            "action": f"Book Flight {flight_id} & Hotel {hotel_id} (Client Credit Card Charged, Discount applied: {loyalty_discount*100}%)",
            "cost_usd": 0.00,
            "status": "SUCCESS"
        })
        ctx.state['payment_ledger'] = ledger
        return Event(actions=EventActions(route='paid'), output=f"External booking payment of ${booking_cost} processed (within budget of ${budget}).")
    else:
        ctx.state['payment_status'] = "FAILED_EXCEEDS_BUDGET"
        return Event(actions=EventActions(route='failed'), output=f"Payment failed: booking cost (${booking_cost}) exceeds budget (${budget}).")

@node(name='mcp_booker', rerun_on_resume=True)
async def mcp_booker(ctx: Context) -> str:
    """Confirms flight/hotel bookings via MCP booking tools."""
    hotel_id = ctx.state.get('selected_hotel_id')
    flight_id = ctx.state.get('selected_flight_id')
    
    charge_agent_payment(ctx, "mcp_booking_agent", f"Confirm booking for hotel ID {hotel_id} & flight {flight_id}", 0.20)
    
    prompt = f"Book hotel ID {hotel_id} and flight {flight_id} using the confirm_booking tool."
    res = await ctx.run_node(mcp_booking_agent, prompt)
    
    ctx.state['booking_status'] = res
    
    return res

@node(name='itinerary_planner', rerun_on_resume=True)
async def itinerary_planner(ctx: Context) -> Event:
    """Plans the daily itinerary and appends the agent payment ledger transaction breakdown."""
    destination = ctx.state.get('destination')
    dates = ctx.state.get('dates')
    booking_status = ctx.state.get('booking_status', 'No booking confirmed.')
    payment_status = ctx.state.get('payment_status', 'UNPAID')
    weather_forecast = ctx.state.get('weather_forecast', 'No forecast details.')
    discount = ctx.state.get('loyalty_discount', 0.0)
    
    charge_agent_payment(ctx, "itinerary_agent", "Generate day-by-day travel itinerary", 0.10)
    
    prompt = (
        f"Plan a travel itinerary for {destination} on {dates}. "
        f"Booking info: {booking_status}. "
        f"Weather details to incorporate: {weather_forecast}. "
        f"Applied loyalty discount: {discount*100}%."
    )
    res = await ctx.run_node(itinerary_agent, prompt)
    
    # Format the Agentic Payment Ledger
    ledger = ctx.state.get('payment_ledger', [])
    balance = ctx.state.get('agent_wallet_balance', 10.00)
    
    ledger_str = "\n\n### 💳 Agentic Payments Ledger (x402 / MPP Protocol)\n"
    ledger_str += "| Agent Name | Action | Cost (USD) | Status |\n"
    ledger_str += "| :--- | :--- | :--- | :--- |\n"
    for tx in ledger:
        status_icon = "🟢 SUCCESS" if tx.get('status') == "SUCCESS" else ("🟡 PENDING" if tx.get('status') == "PENDING" else "🔴 FAILED")
        cost_val = tx.get('cost_usd', 0.0)
        cost_display = f"${cost_val:.2f}" if cost_val > 1.0 else f"${cost_val:.4f}"
        ledger_str += f"| `{tx.get('agent_name')}` | {tx.get('action')} | {cost_display} | {status_icon} |\n"
        
    ledger_str += f"\n**Remaining Agent Wallet Balance**: `${balance:.4f} USD` (Initial: `$10.0000 USD`)\n"
    ledger_str += f"**Final Booking Payment Status**: `{payment_status}`\n"
    
    final_output = res + ledger_str
    ctx.state['itinerary'] = final_output
    
    return Event(message=final_output)

# ---------------------------------------------------------------------------
# 7. Workflow Graph Assembly
# ---------------------------------------------------------------------------
root_agent = Workflow(
    name='root_agent',
    state_schema=TravelState,
    edges=[
        ('START', extract_preferences),
        (extract_preferences, {
            'valid': currency_conversion,
            'invalid': explain_agent
        }),
        (currency_conversion, {
            'success': fetch_weather,
            'payment_failed': explain_agent
        }),
        (fetch_weather, search_listings),
        (search_listings, route_decision),
        (route_decision, {
            'book': apply_loyalty_discount,
            'itinerary': itinerary_planner
        }),
        (apply_loyalty_discount, validate_payment),
        (validate_payment, {
            'paid': mcp_booker,
            'failed': itinerary_planner
        }),
        (mcp_booker, itinerary_planner)
    ]
)
