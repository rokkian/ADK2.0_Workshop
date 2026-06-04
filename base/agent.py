"""
Step 1: Skeleton of a bare basic ADK Agent.
"""

from google.adk.agents.llm_agent import Agent

root_agent = Agent(
    model="gemini-2.5-flash",
    name="root_agent",
    description="A helpful assistant for user questions.",
    instruction="Answer user questions to the best of your knowledge, nothing specific.",
)
