"""
Ambitious Multi-Agent A2A Server for Travel Planner v2
======================================================
This script launches 4 distinct A2A agents on different ports:
1. Currency Converter (Port 8006) - Requires 0.05 USD (via x402)
2. Weather Forecaster (Port 8007) - Requires 0.02 USD (via x402)
3. Payment Escrow (Port 8008) - Free (Manages wallet balances and issues proofs)
4. Loyalty Discounts (Port 8009) - Requires 0.03 USD (via x402)
"""

import os
import time
import logging
import threading
from pathlib import Path
from dotenv import load_dotenv

# Load env variables
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path, override=True)

# Force Gemini Developer API
os.environ['GOOGLE_GENAI_USE_VERTEXAI'] = '0'
if 'GOOGLE_API_KEY' in os.environ:
    os.environ['GEMINI_API_KEY'] = os.environ['GOOGLE_API_KEY']

import uvicorn
from pydantic import BaseModel, Field
from a2a.types import AgentCard, AgentCapabilities, AgentSkill
from google.adk.agents.llm_agent import Agent
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.a2a.executor.a2a_agent_executor import A2aAgentExecutor
from a2a.server.request_handlers.default_request_handler import DefaultRequestHandler
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.server.apps.rest.fastapi_app import A2ARESTFastAPIApplication

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("travel_a2a")

# ---------------------------------------------------------------------------
# Global Shared Wallet Ledger (In-Memory because all servers run in the same process)
# ---------------------------------------------------------------------------
WALLETS = {
    "client_supervisor_wallet": 10.00,
    "wallet_currency_agent": 0.00,
    "wallet_weather_agent": 0.00,
    "wallet_loyalty_agent": 0.00,
}

def execute_escrow_action(action: str, from_wallet: str, to_wallet: str = "", amount_usd: float = 0.0) -> str:
    """Modifies global wallet balances and returns transaction receipt details."""
    global WALLETS
    print(f"DEBUG ESCROW TOOL CALL: action={action}, from_wallet={from_wallet}, to_wallet={to_wallet}, amount_usd={amount_usd}", flush=True)
    action = action.strip().lower()
    
    if action == "get_balance":
        bal = WALLETS.get(from_wallet, 0.0)
        return f"Wallet {from_wallet} balance is ${bal:.4f} USD."
        
    elif action == "transfer":
        curr_bal = WALLETS.get(from_wallet, 0.0)
        if curr_bal < amount_usd:
            return f"FAILED: Insufficient funds. Wallet {from_wallet} has ${curr_bal:.4f} but requires ${amount_usd:.4f}."
            
        WALLETS[from_wallet] = round(curr_bal - amount_usd, 4)
        if to_wallet:
            WALLETS[to_wallet] = round(WALLETS.get(to_wallet, 0.0) + amount_usd, 4)
            
        proof = f"PROOF-VAL-TX-{from_wallet[:4]}-{to_wallet[:4]}-{int(amount_usd*1000)}"
        return f"SUCCESS: Transferred ${amount_usd:.4f} from {from_wallet} to {to_wallet}. New balance of {from_wallet} is ${WALLETS[from_wallet]:.4f}. Payment Proof: {proof}"
        
    return "FAILED: Unknown action"

# ---------------------------------------------------------------------------
# 1. Currency Converter Agent (Port 8006)
# ---------------------------------------------------------------------------
class CurrencyResponse(BaseModel):
    status: str = Field(description="SUCCESS or 402_PAYMENT_REQUIRED")
    converted_amount: float = Field(default=0.0, description="Converted amount in USD")
    rate: float = Field(default=1.0, description="Conversion rate used")
    fee_usd: float = Field(default=0.05, description="Transaction fee required")
    destination_wallet: str = Field(default="wallet_currency_agent", description="Escrow deposit address")
    challenge: str = Field(default="CHALLENGE-CURR-9988", description="Unique challenge code")

currency_agent = Agent(
    model="gemini-2.5-flash",
    name="currency_converter",
    description="A specialist agent that converts foreign currency to USD (requires x402 payment).",
    instruction=(
        "You are a currency converter agent. "
        "Input will be a JSON string with 'query' and optionally 'payment_proof'. "
        "If 'payment_proof' is not provided, or does not start with 'PROOF-VAL-', you MUST return a response with: "
        "status='402_PAYMENT_REQUIRED', fee_usd=0.05, destination_wallet='wallet_currency_agent', and challenge='CHALLENGE-CURR-9988'. "
        "If a valid 'payment_proof' starting with 'PROOF-VAL-' is provided, parse the query (e.g. 'Convert 1000 EUR to USD'), "
        "perform conversion (EUR=1.08, GBP=1.27, JPY=0.0064, others=1.0), and return status='SUCCESS' with the converted_amount and rate."
    ),
    output_schema=CurrencyResponse
)

# ---------------------------------------------------------------------------
# 2. Weather Forecaster Agent (Port 8007)
# ---------------------------------------------------------------------------
class WeatherResponse(BaseModel):
    status: str = Field(description="SUCCESS or 402_PAYMENT_REQUIRED")
    forecast: str = Field(default="", description="Detailed day-by-day weather forecast and packing tips")
    fee_usd: float = Field(default=0.02, description="Transaction fee required")
    destination_wallet: str = Field(default="wallet_weather_agent", description="Escrow deposit address")
    challenge: str = Field(default="CHALLENGE-WEATH-7766", description="Unique challenge code")

weather_agent = Agent(
    model="gemini-2.5-flash",
    name="weather_forecaster",
    description="A specialist agent that provides weather forecasts for destinations (requires x402 payment).",
    instruction=(
        "You are a weather forecaster agent. "
        "Input will be a JSON string with 'query' (destination city/dates) and optionally 'payment_proof'. "
        "If 'payment_proof' is not provided, or does not start with 'PROOF-VAL-', you MUST return a response with: "
        "status='402_PAYMENT_REQUIRED', fee_usd=0.02, destination_wallet='wallet_weather_agent', and challenge='CHALLENGE-WEATH-7766'. "
        "If a valid 'payment_proof' starting with 'PROOF-VAL-' is provided, generate a detailed weather forecast for the city "
        "and date range, list expected high/low temperatures, rain probabilities, and packing tips. "
        "Set status='SUCCESS' and put the details in the 'forecast' field."
    ),
    output_schema=WeatherResponse
)

# ---------------------------------------------------------------------------
# 3. Agentic Payment Escrow Agent (Port 8008)
# ---------------------------------------------------------------------------
class EscrowResponse(BaseModel):
    status: str = Field(description="SUCCESS or FAILED")
    payment_proof: str = Field(default="", description="Unique payment receipt token")
    remaining_balance: float = Field(default=0.0, description="Remaining balance of the payer wallet")
    message: str = Field(description="Transaction status message")

payment_escrow_agent = Agent(
    model="gemini-2.5-flash",
    name="payment_escrow",
    description="Handles machine-to-machine wallet operations and x402 payment verification.",
    instruction=(
        "You are the Payment Escrow Agent. You manage agent wallet accounts. "
        "You have a tool 'execute_escrow_action' to query balances and process transfers. "
        "Input will be a JSON containing 'action' ('get_balance' or 'transfer'), 'from_wallet', 'to_wallet', 'amount_usd', and 'challenge'. "
        "You MUST pass the exact 'from_wallet', 'to_wallet', and 'amount_usd' values from the input JSON to the 'execute_escrow_action' tool arguments. "
        "Do NOT change or hallucinate these wallet names (for example, do NOT use 'wallet_payment_escrow' unless it is explicitly passed as 'from_wallet' in the input). "
        "Call execute_escrow_action tool to run the transaction, then parse its response to return status, payment_proof, remaining_balance, and message."
    ),
    tools=[execute_escrow_action],
    output_schema=EscrowResponse
)

# ---------------------------------------------------------------------------
# 4. Loyalty Discounts Agent (Port 8009)
# ---------------------------------------------------------------------------
class LoyaltyResponse(BaseModel):
    status: str = Field(description="SUCCESS or 402_PAYMENT_REQUIRED")
    discount_rate: float = Field(default=0.0, description="Discount multiplier (e.g. 0.10 for 10% off)")
    message: str = Field(default="", description="Details of the applied loyalty discount")
    fee_usd: float = Field(default=0.03, description="Transaction fee required")
    destination_wallet: str = Field(default="wallet_loyalty_agent", description="Escrow deposit address")
    challenge: str = Field(default="CHALLENGE-LOYAL-5544", description="Unique challenge code")

loyalty_agent = Agent(
    model="gemini-2.5-flash",
    name="loyalty_discounts",
    description="Calculates customer loyalty discounts on bookings (requires x402 payment).",
    instruction=(
        "You are a loyalty discounts agent. "
        "Input will be a JSON string with 'query' (e.g. hotel ID, user tier) and optionally 'payment_proof'. "
        "If 'payment_proof' is not provided, or does not start with 'PROOF-VAL-', you MUST return a response with: "
        "status='402_PAYMENT_REQUIRED', fee_usd=0.03, destination_wallet='wallet_loyalty_agent', and challenge='CHALLENGE-LOYAL-5544'. "
        "If a valid 'payment_proof' starting with 'PROOF-VAL-' is provided, parse the tier (assume VIP if not specified). "
        "Calculate discount (VIP gets 0.15 i.e. 15% discount, Gold gets 0.10, Silver gets 0.05, others 0.0). "
        "Return status='SUCCESS', discount_rate, and a descriptive message."
    ),
    output_schema=LoyaltyResponse
)

# ---------------------------------------------------------------------------
# Helper function to configure and run an A2A agent app
# ---------------------------------------------------------------------------
def make_a2a_app(agent_obj: Agent, name: str, port: int, skills: list):
    runner = Runner(
        agent=agent_obj, 
        app_name=f"a2a_{name}_service", 
        session_service=InMemorySessionService()
    )
    executor = A2aAgentExecutor(runner=runner)
    task_store = InMemoryTaskStore()
    handler = DefaultRequestHandler(agent_executor=executor, task_store=task_store)
    
    card = AgentCard(
        name=name,
        description=agent_obj.description,
        version="2.0.0",
        preferred_transport="HTTP+JSON",
        url=f"http://localhost:{port}/",
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=skills,
    )
    
    a2a_app = A2ARESTFastAPIApplication(agent_card=card, http_handler=handler)
    return a2a_app.build()

# Build the 4 Apps
app_curr = make_a2a_app(currency_agent, "currency_converter", 8006, [
    AgentSkill(id="convert", name="Convert Currency", description="Convert foreign currency to USD", tags=["finance"])
])
app_weath = make_a2a_app(weather_agent, "weather_forecaster", 8007, [
    AgentSkill(id="weather", name="Weather Forecast", description="Get weather for destination", tags=["weather"])
])
app_escrow = make_a2a_app(payment_escrow_agent, "payment_escrow", 8008, [
    AgentSkill(id="escrow", name="Payment Escrow", description="Authorize machine payments", tags=["payment"])
])
app_loyal = make_a2a_app(loyalty_agent, "loyalty_discounts", 8009, [
    AgentSkill(id="loyalty", name="Loyalty Discount", description="Get discounts for hotels", tags=["loyalty"])
])

def run_uvicorn(app, port):
    logger.info(f"Starting A2A agent on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")

if __name__ == "__main__":
    t1 = threading.Thread(target=run_uvicorn, args=(app_curr, 8006), daemon=True)
    t2 = threading.Thread(target=run_uvicorn, args=(app_weath, 8007), daemon=True)
    t3 = threading.Thread(target=run_uvicorn, args=(app_escrow, 8008), daemon=True)
    t4 = threading.Thread(target=run_uvicorn, args=(app_loyal, 8009), daemon=True)
    
    t1.start()
    t2.start()
    t3.start()
    t4.start()
    
    logger.info("All 4 A2A Servers started successfully!")
    while True:
        try:
            time.sleep(1)
        except KeyboardInterrupt:
            break
