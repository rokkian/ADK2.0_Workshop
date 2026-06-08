# ADK 2.0 Agentic Coding Workshop

Welcome to the **Agent Development Kit (ADK) 2.0** hands-on workshop repository.

This repository is a step-by-step developer guide introducing the modular, graph-based architecture of ADK 2.0. You will learn how to build, run, test, and orchestrate advanced agent workflows, integrate external APIs via the Model Context Protocol (MCP), communicate between distributed agents via the Agent-to-Agent (A2A) protocol, and manage session state, memory, and persistence across conversations.

---

## 🏗️ Core Concepts of ADK 2.0

ADK 2.0 shifts agent orchestration from traditional linear loops to a robust, event-driven graph execution engine:

*   **`Agent`**: Modular LLM-backed building blocks, each with a model, instructions, and tools.
*   **`Workflow`**: A graph-based execution container defining nodes and the edges/transitions between them.
*   **`@node (FunctionNode)`**: Python functions decorated to run custom logic (routing, data extraction, API parsing) inside a workflow graph.
*   **`Event` & `EventActions`**: Data structures used to communicate routing forks, state deltas, or user-facing content across nodes.
*   **`McpToolset`**: Exposes external tools and APIs to agents using the industry-standard **Model Context Protocol (MCP)**.
*   **`RemoteA2aAgent`**: Connects to a remote agent microservice over the **Agent-to-Agent (A2A)** protocol.
*   **Session State**: Four-scoped key-value store (`session`, `user`, `app`, `temp`) shared across all nodes in a workflow.
*   **Memory & Persistence**: Cross-session knowledge via `MemoryService`; durable sessions via `DatabaseSessionService`.

---

## 📂 Workshop Structure

```
lesson_1_adk_agents/        ← Steps 1–7: building agents from scratch to production
lesson_2_sessions_memory/   ← Steps 8–11: state, callbacks, memory, and persistence
```

---

## 📖 Lesson 1 — ADK Agents (`lesson_1_adk_agents/`)

### Step 1 — [`base`](lesson_1_adk_agents/base/agent.py)
**Topic**: Bare Basic Agent  
Skeleton of a simple standalone assistant to verify environment connectivity.

### Step 2 — [`standard`](lesson_1_adk_agents/standard/agent.py)
**Topic**: Standard LLM Agent  
A model-instructed agent that handles direct queries and answers general questions.

### Step 3 — [`modern`](lesson_1_adk_agents/modern/agent.py)
**Topic**: Graph Workflows  
Introduces the ADK 2.0 graph engine. A conditional routing `Workflow` with `@node` that splits requests between a general assistant and a math specialist.

### Step 4 — [`mcp_agent`](lesson_1_adk_agents/mcp_agent/agent.py)
**Topic**: Model Context Protocol (MCP) Tools  
Connects an agent to a local stdio-based filesystem MCP server to read and write files directly.

### Step 5 — [`a2a_agent`](lesson_1_adk_agents/a2a_agent/README.md)
**Topic**: Distributed Agent-to-Agent (A2A) Architecture  
A distributed agent microservice consisting of:
- [`server.py`](lesson_1_adk_agents/a2a_agent/server.py): Exposes a local agent over FastAPI with A2A REST endpoints and an `AgentCard` manifest.
- [`agent.py`](lesson_1_adk_agents/a2a_agent/agent.py): Uses `RemoteA2aAgent` to query the remote specialist dynamically.

### Step 6 — [`travel_planner`](lesson_1_adk_agents/travel_planner/agent.py)
**Topic**: Complex Orchestrated Travel Agent  
A production-grade orchestration combining all building blocks:
- Shared memory via `TravelState` Pydantic schema.
- Conditional routing (`extract_preferences`, `route_decision` nodes).
- Dynamic worker execution (`ctx.run_node`).
- Custom MCP travel server ([`mcp_travel_server.py`](lesson_1_adk_agents/travel_planner/mcp_travel_server.py)).
- Early capability disclosure when required inputs are missing.

### Step 7 — [`travel_planner_v2`](lesson_1_adk_agents/travel_planner_v2/agent.py)
**Topic**: Advanced Multi-Agent Travel Planner — MCP + A2A + Agentic Payments  
An ambitious end-to-end showcase combining every ADK 2.0 feature:

- **5 MCP servers** (stdio subprocesses): Travel API, Airbnb listings, Flights database, TripAdvisor-style reviews, live Wikipedia info.
- **4 remote A2A microservices**: Currency Converter, Weather Forecaster, Payment Escrow, Loyalty Discounts — each on a dedicated port.
- **x402 / MPP Agentic Payments**: the workflow holds an in-memory agent wallet; premium A2A agents issue `402_PAYMENT_REQUIRED` challenges; the supervisor negotiates with the Escrow agent to produce a payment proof token, then retries — fully machine-to-machine.
- **Multi-currency support**: budgets in EUR/GBP/JPY are normalised to USD via the A2A Currency agent before any pricing decision.
- **Loyalty discounts**: a dedicated A2A agent applies VIP/Gold/Silver tier discounts before confirming bookings.
- **Full payment ledger**: every micro-transaction is logged and displayed in the final itinerary.

| File | Purpose |
|---|---|
| [`agent.py`](lesson_1_adk_agents/travel_planner_v2/agent.py) | Root `Workflow` — 10 nodes, conditional routing, x402 logic |
| [`run_a2a_servers.py`](lesson_1_adk_agents/travel_planner_v2/run_a2a_servers.py) | Launches all 4 A2A agents in one process |
| [`mcp_travel_server.py`](lesson_1_adk_agents/travel_planner_v2/mcp_travel_server.py) | Flight & hotel search + booking confirmation |
| [`mcp_airbnb_server.py`](lesson_1_adk_agents/travel_planner_v2/mcp_airbnb_server.py) | Airbnb-style property listings |
| [`mcp_flights_server.py`](lesson_1_adk_agents/travel_planner_v2/mcp_flights_server.py) | Flight database with multi-airline results |
| [`mcp_wikipedia_server.py`](lesson_1_adk_agents/travel_planner_v2/mcp_wikipedia_server.py) | Live Wikipedia REST API (static fallback for 12 cities) |
| [`currency_a2a_server.py`](lesson_1_adk_agents/travel_planner_v2/currency_a2a_server.py) | Standalone currency A2A server (x402, port 8006) |

---

## 📖 Lesson 2 — Sessions, Memory & Persistence (`lesson_2_sessions_memory/`)

### Step 8 — [`session_state`](lesson_2_sessions_memory/session_state/agent.py)
**Topic**: Session State & Agent Context  
A shopping cart assistant demonstrating all four ADK state scopes:

| Prefix | Scope | Lifetime |
|---|---|---|
| `state["key"]` | Session | This conversation only |
| `state["user:key"]` | User | All sessions for this user |
| `state["app:key"]` | App | All users of the application |
| `state["temp:key"]` | Temp | Discarded after current LLM invocation |

### Step 9 — [`callbacks`](lesson_2_sessions_memory/callbacks/agent.py)
**Topic**: Callbacks — Observe, Customize, and Control Agent Behavior  
Six lifecycle hooks that let you intercept execution without changing agent logic:

| Callback | Fires | Returning a value… |
|---|---|---|
| `before_agent_callback` | Before the agent turn | Skips the entire turn |
| `after_agent_callback` | After the agent turn | — |
| `before_model_callback` | Before each LLM call | Skips the LLM call (e.g. cache hit) |
| `after_model_callback` | After each LLM response | Replaces the model output |
| `before_tool_callback` | Before each tool call | Skips the tool (e.g. serve from cache) |
| `after_tool_callback` | After each tool call | — |

### Step 10 — [`memory`](lesson_2_sessions_memory/memory/agent.py)
**Topic**: Cross-Session Knowledge with `InMemoryMemoryService`  
Demonstrates the two memory layers in ADK:
- **Session state** — scratchpad for one conversation, lost when the session ends.
- **Memory service** — searchable knowledge store spanning many past sessions, populated via `add_session_to_memory()` and queried with `search_memory()`.

### Step 11 — [`persistence`](lesson_2_sessions_memory/persistence/agent.py)
**Topic**: Durable Sessions with `DatabaseSessionService` (SQLite)  
Shows how to replace `InMemorySessionService` with a SQLAlchemy-backed store so conversations survive process restarts.

| Service | Config | Data |
|---|---|---|
| `InMemorySessionService` | Zero config | Lost on restart |
| `DatabaseSessionService` | `sqlite+aiosqlite:///./sessions.db` | Persists forever |
| `VertexAiSessionService` | Google Cloud | Fully managed |

---

## 🚀 Setup & Execution Guide

### Prerequisites
Install [uv](https://github.com/astral-sh/uv), then create a `.env` file in the root directory:
```bash
GOOGLE_API_KEY="your-gemini-api-key"
```

### Running via ADK CLI
```bash
# Syntax: uv run adk run <path/to/agent>
uv run adk run lesson_1_adk_agents/base
uv run adk run lesson_1_adk_agents/travel_planner "Plan a trip to Tokyo, budget $2000"
uv run adk run lesson_2_sessions_memory/session_state
```

### Running the Web UI
```bash
uv run adk web .
```
Navigate to `http://localhost:8000` and select any agent from the dropdown.

### Running the A2A Example (Step 5)
```bash
# Terminal 1 — start the remote agent server
uv run python lesson_1_adk_agents/a2a_agent/server.py

# Terminal 2 — run the client or open the Web UI
uv run python lesson_1_adk_agents/a2a_agent/client.py
```

### Running the Advanced Travel Planner v2 (Step 7)
The four A2A microservices must be running before starting the agent.

```bash
# Terminal 1 — start all A2A servers (keep running)
uv run python lesson_1_adk_agents/travel_planner_v2/run_a2a_servers.py

# Terminal 2 — run the agent
uv run adk run lesson_1_adk_agents/travel_planner_v2
# or open the Web UI: uv run adk web .
```

Try this query to exercise the full payment flow:
```
Plan a trip to Tokyo from July 10-17 with a budget of 1500 EUR
```
The agent will: convert EUR → USD (x402 payment) → fetch weather (x402) → search 5 MCP servers → decide on booking → apply loyalty discount → validate payment → generate a day-by-day itinerary with a full transaction ledger.

### Running the Persistence Example (Step 11)
```bash
uv run python lesson_2_sessions_memory/persistence/run_with_persistence.py
```
