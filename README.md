# ADK 2.0 Agentic Coding Workshop

Welcome to the **Agent Development Kit (ADK) 2.0** hands-on workshop repository. 

This repository contains a step-by-step developer guide designed to introduce you to the modular, graph-based architecture of ADK 2.0. By going through these directories, you will learn how to build, run, test, and orchestrate advanced agent workflows, integrate external APIs via the Model Context Protocol (MCP), and communicate between distributed agents via the Agent-to-Agent (A2A) protocol.

---

## 🏗️ Core Concepts of ADK 2.0

ADK 2.0 shifts agent orchestration from traditional linear loops to a robust, event-driven graph execution engine:

*   **`Agent`**: The modular building blocks of LLM-backed intelligence, defined with a specific model, instructions, and tools.
*   **`Workflow`**: A graph-based execution container defining execution nodes and the edges/transitions between them.
*   **`@node (FunctionNode)`**: Standard Python functions wrapped to run custom logic (e.g. data extraction, conditional routing, API parsing) inside a workflow graph.
*   **`Event` & `EventActions`**: Custom data structures used to communicate routing forks, state deltas, or user-facing content across workflow nodes.
*   **`McpToolset`**: Exposes external tools and APIs dynamically to agents using the industry-standard **Model Context Protocol (MCP)**.

---

## 📂 Workshop Roadmap & Content

The workshop is divided into 6 progressive steps, each demonstrating a different aspect of the framework:

### 1. [base](file:///home/mrocc/adk2_workshop/base/agent.py)
*   **Topic**: Bare Basic Agent
*   **Description**: Skeleton of a simple, standalone assistant agent to verify basic environment connectivity.

### 2. [standard](file:///home/mrocc/adk2_workshop/standard/agent.py)
*   **Topic**: Standard LLM Agent
*   **Description**: A standard model-instructed agent that handles direct queries and answers general questions.

### 3. [modern](file:///home/mrocc/adk2_workshop/modern/agent.py)
*   **Topic**: Graph Workflows
*   **Description**: Introduces the new ADK 2.0 graph engine. Demonstrates a conditional routing workflow (`Workflow` with `@node`) that splits requests between a general assistant and a math specialist.

### 4. [mcp_agent](file:///home/mrocc/adk2_workshop/mcp_agent/agent.py)
*   **Topic**: Model Context Protocol (MCP) Tools
*   **Description**: Demonstrates how to connect an agent to a local stdio-based filesystem MCP server (`@modelcontextprotocol/server-filesystem`) to read and write files directly.

### 5. [a2a_agent](file:///home/mrocc/adk2_workshop/a2a_agent/README.md)
*   **Topic**: Distributed Agent-to-Agent (A2A) Architecture
*   **Description**: Showcases setting up a distributed agent microservice. Consists of:
    - [server.py](file:///home/mrocc/adk2_workshop/a2a_agent/server.py): Exposes a local agent over FastAPI with A2A REST endpoints and publishes an `AgentCard` metadata manifest.
    - [client.py](file:///home/mrocc/adk2_workshop/a2a_agent/client.py) & [agent.py](file:///home/mrocc/adk2_workshop/a2a_agent/agent.py): Uses `RemoteA2aAgent` to query the remote specialist agent dynamically using its metadata card.

### 6. [travel_planner](file:///home/mrocc/adk2_workshop/travel_planner/agent.py)
*   **Topic**: Complex Orchestrated Travel Agent
*   **Description**: A production-grade orchestration showing how all pieces fit together. Features:
    - Shared memory (`TravelState` schema validation).
    - Custom routing logic (`extract_preferences`, `route_decision` nodes).
    - Dynamic worker node execution (`ctx.run_node`).
    - Tool integration via a local custom travel server ([mcp_travel_server.py](file:///home/mrocc/adk2_workshop/travel_planner/mcp_travel_server.py)).
    - Automatic verification of missing parameters (exposing capability descriptions early to prevent redundant API operations).

---

## 🚀 Setup & Execution Guide

### Prerequisites
Make sure you have [uv](https://github.com/astral-sh/uv) (Python package manager) installed. 

Create a `.env` file in the root directory and add your Google AI Studio API Key:
```bash
GOOGLE_API_KEY="your-gemini-api-key"
```

### Running via ADK CLI (Interactive Run)
You can run any local agent directory directly in your terminal using the ADK CLI:
```bash
# General Syntax: uv run adk run <agent-directory> "[optional query]"
# Example (Base Agent):
uv run adk run base

# Example (Travel Planner):
uv run adk run travel_planner "Plan a trip to Tokyo for next week, budget $2000"
```

### Running the Web UI Interface
ADK includes a built-in FastAPI web runner with an interactive chat interface to let you select and play with any of the agents:
```bash
# Start the web UI server
uv run adk web .
```
Once started, navigate to the local URL (usually `http://localhost:8000`) in your browser to start interacting.

### Running A2A Example
1. Start the server (terminal 1):
   ```bash
   uv run python a2a_agent/server.py
   ```
2. Run the client (terminal 2) or load it in the Web UI:
   ```bash
   uv run python a2a_agent/client.py
   ```
