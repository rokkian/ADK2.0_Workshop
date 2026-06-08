"""
ADK Workshop Step 4: External MCP Tools
=======================================

This module demonstrates integrating Model Context Protocol (MCP) tools into the ADK.
Specifically, it showcases:
1. McpToolset: The ADK class managing MCP client sessions and importing tools.
2. StdioConnectionParams: Managing stdio-based subprocess communication for local MCP servers.
3. StdioServerParameters: Parameters to start a process (e.g. running 'npx' or 'uvx' commands).

Why these elements were used:
-----------------------------
- Model Context Protocol (MCP) provides a standard protocol to expose resources, prompts,
  and tools to LLM models. By using `McpToolset`, the ADK acts as an MCP Client.
- The `McpToolset` connects to the server, queries its tool definitions, converts them
  into native ADK `BaseTool` declarations, and handles calling those tools under the hood.
- `StdioConnectionParams` and `StdioServerParameters` run a local server process
  (in this case, launching node-based `@modelcontextprotocol/server-filesystem` via `npx`).
  The ADK spawns this server, communicates via stdin/stdout redirection, and handles
  automatic server teardown when the agent session closes.
"""

from google.adk.agents.llm_agent import Agent
from google.adk.tools import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

# Initialize the MCP toolset to connect to the filesystem server
filesystem_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="npx",
            args=[
                "-y",
                "@modelcontextprotocol/server-filesystem",
                "/home/mrocc/adk2_workshop",
            ],
        )
    )
)

# Define the agent and pass the toolset into the tools list
root_agent = Agent(
    model="gemini-2.5-flash",
    name="mcp_agent",
    description="An agent that can access and manipulate the filesystem using MCP.",
    instruction="You are a filesystem assistant. You have access to the local workshop directory. Use the filesystem tools to list, read, or write files as requested by the user.",
    tools=[filesystem_toolset],
)
