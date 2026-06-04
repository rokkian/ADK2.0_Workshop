"""
ADK Workshop Step 5: A2A Agent Client
=====================================

This module exposes the Remote A2a client agent to the ADK framework.
Exposing it as `root_agent` in `agent.py` allows the ADK CLI (`adk run`)
and ADK Web UI (`adk web`) to load and run it interactively.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent

# Load environment variables from the root .env file if it exists
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path, override=True)

# Force Gemini Developer API (using API Key) instead of Vertex AI
os.environ['GOOGLE_GENAI_USE_VERTEXAI'] = '0'
if 'GOOGLE_API_KEY' in os.environ:
    os.environ['GEMINI_API_KEY'] = os.environ['GOOGLE_API_KEY']

# Define the root agent representing the client calling the remote A2A specialist
root_agent = RemoteA2aAgent(
    name="joke_specialist_client",
    agent_card="http://localhost:8005/.well-known/agent-card.json",
)
