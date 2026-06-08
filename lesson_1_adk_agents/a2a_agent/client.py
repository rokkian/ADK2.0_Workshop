"""
ADK Workshop Step 5: A2A Client
==============================

This module demonstrates building an A2A client runner that calls a remote A2A specialist agent.
Specifically, it showcases:
1. RemoteA2aAgent: An ADK agent implementation that interacts with remote agents via the A2A client SDK.
2. Runner: Orchestrates running the remote agent.
3. auto_create_session=True: Runner parameter ensuring the session is generated if missing.
4. InMemorySessionService: Local session state manager.

Why these elements were used:
-----------------------------
- `RemoteA2aAgent` is an experimental agent class that acts as a client wrapper. It resolves
  the remote agent's manifest (`AgentCard`) by downloading it from the provided URL
  (`http://localhost:8000/.well-known/agent-card.json`).
- Once resolved, it knows which transport protocol and endpoints the remote server uses.
- When the client's `Runner` executes `run_async()`, `RemoteA2aAgent` packages the message
  into A2A-compliant formats (like `SendMessageRequest`), sends it to the remote server, and
  returns the results as standard ADK events.
- By wrapping the remote agent in `RemoteA2aAgent`, we can treat it just like any local
  agent or tool, simplifying supervisor-specialist multi-agent orchestration.
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

import asyncio
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types


async def main():
    # 1. Define the remote agent targeting the local server's agent card
    remote_agent = RemoteA2aAgent(
        name="joke_specialist_client",
        agent_card="http://localhost:8005/.well-known/agent-card.json",
    )

    # 2. Define the Runner to execute the remote agent, enabling session auto-creation
    runner = Runner(
        agent=remote_agent,
        app_name="joke_client_app",
        session_service=InMemorySessionService(),
        auto_create_session=True,
    )

    print("Sending request to remote A2A agent...")
    query = "Tell me a short joke about a computer mouse."

    # Run the agent asynchronously and collect events
    async for event in runner.run_async(
        user_id="test_user",
        session_id="client_session_1",
        new_message=types.Content(parts=[types.Part.from_text(text=query)]),
    ):
        # Print final outputs or agent messages
        if event.output is not None:
            print(f"\nFinal Response from Remote Agent:\n{event.output}")
        elif event.content is not None:
            text = "".join(part.text for part in event.content.parts if part.text)
            if text:
                print(f"\nAgent Message:\n{text}")


if __name__ == "__main__":
    asyncio.run(main())
