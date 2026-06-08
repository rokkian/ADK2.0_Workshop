"""
ADK Workshop Step 6: A2A Currency Conversion Server (standalone)
=================================================================

Exposes a single currency-converter A2A agent implementing the x402 payment
challenge protocol on port 8006.

NOTE: For the full multi-agent demo (currency + weather + escrow + loyalty),
      run  `run_a2a_servers.py`  instead — it starts all four servers in one
      process and shares a live in-memory wallet.  This file is a self-contained
      reference for the currency agent only.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path, override=True)

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


# ---------------------------------------------------------------------------
# x402 response schema (mirrors the pattern in run_a2a_servers.py)
# ---------------------------------------------------------------------------
class CurrencyResponse(BaseModel):
    status: str = Field(description="SUCCESS or 402_PAYMENT_REQUIRED")
    converted_amount: float = Field(default=0.0, description="Converted amount in USD")
    rate: float = Field(default=1.0, description="Conversion rate used")
    fee_usd: float = Field(default=0.05, description="Transaction fee required in USD")
    destination_wallet: str = Field(default="wallet_currency_agent", description="Payment destination")
    challenge: str = Field(default="CHALLENGE-CURR-9988", description="Unique challenge token")


currency_agent = Agent(
    model="gemini-2.5-flash",
    name="currency_converter",
    description="A specialist agent that converts foreign currency to USD (requires x402 payment).",
    instruction=(
        "You are a currency converter agent that implements the x402 payment protocol. "
        "Input is a JSON string with 'query' and optionally 'payment_proof'. "
        "If 'payment_proof' is absent or does not start with 'PROOF-VAL-', return: "
        "status='402_PAYMENT_REQUIRED', fee_usd=0.05, destination_wallet='wallet_currency_agent', "
        "challenge='CHALLENGE-CURR-9988'. "
        "If a valid 'payment_proof' starting with 'PROOF-VAL-' is present, parse the query "
        "(e.g. 'Convert 1000 EUR to USD'), apply standard rates "
        "(EUR=1.08, GBP=1.27, JPY=0.0064, others=1.0), and return "
        "status='SUCCESS' with converted_amount and rate."
    ),
    output_schema=CurrencyResponse,
)

runner = Runner(
    agent=currency_agent,
    app_name="a2a_currency_service",
    session_service=InMemorySessionService(),
)
executor = A2aAgentExecutor(runner=runner)
task_store = InMemoryTaskStore()
handler = DefaultRequestHandler(agent_executor=executor, task_store=task_store)

card = AgentCard(
    name="currency_converter",
    description="Converts foreign currency to USD using the x402 payment protocol.",
    version="2.0.0",
    preferred_transport="HTTP+JSON",
    url="http://localhost:8006/",
    capabilities=AgentCapabilities(streaming=False),
    default_input_modes=["text/plain"],
    default_output_modes=["text/plain"],
    skills=[
        AgentSkill(
            id="convert_currency",
            name="Convert Currency",
            description="Convert foreign currency to USD (x402 payment required).",
            tags=["finance", "currency", "x402"],
        )
    ],
)

a2a_app = A2ARESTFastAPIApplication(agent_card=card, http_handler=handler)
app = a2a_app.build()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8006)
