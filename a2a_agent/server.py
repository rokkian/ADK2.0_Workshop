"""
ADK Workshop Step 5: A2A Server
==============================

This module demonstrates exposing a standard ADK Agent as a distributed Agent-to-Agent (A2A) server.
Specifically, it showcases:
1. Agent: The underlying LLM-backed intelligence unit.
2. Runner: The ADK class managing agent execution sessions.
3. A2aAgentExecutor: Bridges the ADK Runner with the A2A task queue and execution lifecycle.
4. DefaultRequestHandler: Processes A2A RPC/REST requests and delegates to the executor.
5. InMemoryTaskStore: In-memory store that tracks the status and progress of A2A tasks.
6. AgentCard: The A2A manifest describing the agent's identity, version, transport, and skills.
7. A2ARESTFastAPIApplication: Generates the FastAPI app exposing standard A2A endpoints.

Why these elements were used:
-----------------------------
- The A2A protocol standardizes how agents discover and call other agents asynchronously.
- The `A2aAgentExecutor` is required to translate incoming A2A messages into ADK input events,
  run the agent's runner, collect agent events, and publish task updates back to the client.
- The `DefaultRequestHandler` and `InMemoryTaskStore` manage http request routing and task state.
- The `AgentCard` is served at `/.well-known/agent-card.json`. It is a machine-readable card
  describing the agent's capabilities, allowing remote supervisors to programmatically discover
  what skills it offers and what transport it uses.
- The `A2ARESTFastAPIApplication` builds a FastAPI app containing the standard A2A routes,
  such as `/v1/message:send` and the agent card endpoint.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from the root .env file if it exists
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path, override=True)

# Force Gemini Developer API (using API Key) instead of Vertex AI
os.environ['GOOGLE_GENAI_USE_VERTEXAI'] = '0'
if 'GOOGLE_API_KEY' in os.environ:
    os.environ['GEMINI_API_KEY'] = os.environ['GOOGLE_API_KEY']

import uvicorn
from a2a.types import AgentCard, AgentCapabilities, AgentSkill
from google.adk.agents.llm_agent import Agent
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.a2a.executor.a2a_agent_executor import A2aAgentExecutor
from a2a.server.request_handlers.default_request_handler import DefaultRequestHandler
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.server.apps.rest.fastapi_app import A2ARESTFastAPIApplication

# Create the underlying LLM agent
agent = Agent(
    model="gemini-2.5-flash",
    name="joke_specialist",
    description="A specialist agent that tells clean, funny jokes.",
    instruction="You are a joke-telling assistant. Tell a funny, clean joke as requested.",
)

# Create the runner
runner = Runner(
    agent=agent, app_name="a2a_joke_service", session_service=InMemorySessionService()
)

# Wrap it in the A2A Agent Executor
executor = A2aAgentExecutor(runner=runner)

# Create the task store and request handler
task_store = InMemoryTaskStore()
handler = DefaultRequestHandler(agent_executor=executor, task_store=task_store)

# Define the A2A Agent Card describing this agent
card = AgentCard(
    name="joke_specialist",
    description="A specialist agent that tells clean, funny jokes.",
    version="1.0.0",
    preferred_transport="HTTP+JSON",
    url="http://localhost:8005/",
    capabilities=AgentCapabilities(streaming=False),
    default_input_modes=["text/plain"],
    default_output_modes=["text/plain"],
    skills=[
        AgentSkill(
            id="tell_joke",
            name="Tell Joke",
            description="Tell a funny, clean joke.",
            tags=["jokes", "fun"],
        )
    ],
)

# Build the FastAPI application implementing A2A endpoints
a2a_app = A2ARESTFastAPIApplication(agent_card=card, http_handler=handler)
app = a2a_app.build()

if __name__ == "__main__":
    # Run the server on port 8005
    uvicorn.run(app, host="0.0.0.0", port=8005)
