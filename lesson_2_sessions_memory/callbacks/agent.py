"""
Phase 2 - Example 2: Callbacks — Observe, Customize, and Control Agent Behavior
=================================================================================

Callbacks let you hook into the agent's execution lifecycle without changing
the agent's core logic. ADK 2.0 provides six callback points:

  before_agent_callback  → fires once before the agent starts processing a turn
  after_agent_callback   → fires once after the agent finishes a turn
  before_model_callback  → fires before every LLM API call
  after_model_callback   → fires after every LLM API response
  before_tool_callback   → fires before every tool execution
  after_tool_callback    → fires after every tool execution

Control Flow — What Returning a Value Does:
-------------------------------------------
  before_agent_callback  returns Content  → SKIPS the entire agent turn
  before_model_callback  returns LlmResponse → SKIPS the LLM call (e.g. for caching)
  after_model_callback   returns LlmResponse → REPLACES the model's output
  before_tool_callback   returns dict     → SKIPS the tool call (e.g. serve from cache)
  after_tool_callback    returns dict     → REPLACES the tool's result
  Returning None (any callback)           → normal execution continues

Exact Parameter Names Are Critical:
------------------------------------
The ADK framework invokes callbacks via keyword arguments. The parameter names
MUST match the values documented here. Using aliases causes a TypeError.

  before/after_agent_callback:  (callback_context: CallbackContext)
  before_model_callback:        (callback_context: CallbackContext, llm_request: LlmRequest)
  after_model_callback:         (callback_context: CallbackContext, llm_response: LlmResponse)
  before_tool_callback:         (tool: BaseTool, args: dict, tool_context: ToolContext)
  after_tool_callback:          (tool: BaseTool, args: dict, tool_context: ToolContext, tool_response: dict)

This Example — A Customer Support Agent with a Full Callback Stack:
-------------------------------------------------------------------
  before_agent_callback  → Rate limiting: prevent more than N turns per session
  before_model_callback  → Guardrail: block forbidden topics before reaching the LLM
  after_model_callback   → Response enrichment: stamp a confidence tag on every reply
  before_tool_callback   → Tool caching: serve repeated identical calls from state
  after_tool_callback    → Audit log: record every tool call + result in session state
  after_agent_callback   → Turn counter: track total turns consumed in this session
"""

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.tools import BaseTool, ToolContext
from google.genai import types as genai_types


# ---------------------------------------------------------------------------
# Configuration constants — easy to tune for a workshop
# ---------------------------------------------------------------------------
MAX_TURNS_PER_SESSION = 10
FORBIDDEN_TOPICS = ["competitor", "lawsuit", "refund fraud", "internal pricing"]
TOOL_CACHE_TTL_TURNS = 3  # reuse a cached tool result for this many turns


# ---------------------------------------------------------------------------
# 1. before_agent_callback — Rate Limiting
# ---------------------------------------------------------------------------
async def rate_limit_callback(callback_context: CallbackContext) -> genai_types.Content | None:
    """
    Runs ONCE before every agent turn.

    Counts how many turns have been used in this session and blocks the agent
    if the limit is exceeded — without touching the LLM or any tools.

    Returning a Content object here SKIPS the agent turn entirely and replies
    with the returned content instead.
    """
    state = callback_context.state

    # Initialize turn counter on first visit.
    if "turns_used" not in state:
        state["turns_used"] = 0

    if state["turns_used"] >= MAX_TURNS_PER_SESSION:
        # Return a Content object to short-circuit the agent.
        return genai_types.Content(
            role="model",
            parts=[genai_types.Part(text=(
                f"Session limit reached ({MAX_TURNS_PER_SESSION} turns). "
                "Please start a new session to continue."
            ))],
        )

    # Returning None allows the agent to proceed normally.
    return None


# ---------------------------------------------------------------------------
# 2. before_model_callback — Content Guardrail + Dynamic Context Injection
# ---------------------------------------------------------------------------
async def guardrail_and_inject_callback(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> LlmResponse | None:
    """
    Runs BEFORE every LLM API call. Use this callback to:
    a) Inspect / mutate the request that will be sent to the model.
    b) Return an LlmResponse to SHORT-CIRCUIT the LLM call entirely.

    Here we do two things:
    1. Scan the latest user message for forbidden topics and block if found.
    2. Inject a dynamic context snippet (user tier) into the system instruction.
    """
    state = callback_context.state
    user_tier = state.get("user:tier", "standard")

    # --- Guardrail: scan the latest user message ---
    latest_user_text = ""
    if llm_request.contents:
        last_content = llm_request.contents[-1]
        if last_content.role == "user" and last_content.parts:
            latest_user_text = " ".join(
                p.text for p in last_content.parts if hasattr(p, "text") and p.text
            ).lower()

    for topic in FORBIDDEN_TOPICS:
        if topic in latest_user_text:
            # Return a pre-built LlmResponse — the LLM is NEVER called.
            return LlmResponse(
                content=genai_types.Content(
                    role="model",
                    parts=[genai_types.Part(text=(
                        f"I'm sorry, I can't discuss '{topic}'. "
                        "Please contact our legal department for this topic."
                    ))],
                )
            )

    # --- Dynamic context injection: mutate the system instruction ---
    # llm_request.config is the GenerateContentConfig sent to the model.
    # We can prepend tier-specific context to the system instruction here.
    tier_context = {
        "premium": "This user has PREMIUM support. Prioritise their request, offer proactive solutions.",
        "standard": "This user has STANDARD support. Be helpful and efficient.",
        "trial": "This user is on a TRIAL plan. Be helpful but mention upgrade options when relevant.",
    }.get(user_tier, "")

    if tier_context and llm_request.config:
        existing_si = llm_request.config.system_instruction or ""
        if isinstance(existing_si, str):
            llm_request.config.system_instruction = f"[USER TIER CONTEXT]: {tier_context}\n\n{existing_si}"

    # Returning None lets the (now-mutated) request proceed to the LLM.
    return None


# ---------------------------------------------------------------------------
# 3. after_model_callback — Response Enrichment
# ---------------------------------------------------------------------------
async def enrich_response_callback(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> LlmResponse | None:
    """
    Runs AFTER every LLM response. Use this to inspect or transform the model's
    output before it is returned to the user.

    Here we count the response tokens and tag the session state with the running
    total — useful for cost tracking — without altering the response content.
    """
    state = callback_context.state

    # Track cumulative model output tokens in session state.
    if llm_response.content and llm_response.content.parts:
        chars = sum(len(p.text) for p in llm_response.content.parts if hasattr(p, "text") and p.text)
        # Rough approximation: 4 chars ≈ 1 token.
        estimated_tokens = chars // 4
        state["session_estimated_output_tokens"] = (
            state.get("session_estimated_output_tokens", 0) + estimated_tokens
        )

    # Returning None keeps the original LlmResponse unchanged.
    # To replace or extend the response, build and return a new LlmResponse here.
    return None


# ---------------------------------------------------------------------------
# 4. before_tool_callback — Tool Result Caching
# ---------------------------------------------------------------------------
def tool_cache_callback(
    tool: BaseTool,
    args: dict,
    tool_context: ToolContext,
) -> dict | None:
    """
    Runs BEFORE every tool execution.

    Implements a simple turn-based cache: if the same tool was called with
    identical arguments in the last N turns, serve the cached result instead
    of re-executing the tool.

    Returning a dict here SKIPS the actual tool call and uses the dict as the
    result. Returning None allows the tool to execute normally.
    """
    # Build a deterministic cache key from tool name + sorted args.
    cache_key = f"temp:cache:{tool.name}:{sorted(args.items())}"
    cached = tool_context.state.get(cache_key)

    if cached is not None:
        cached_result = cached.get("result")
        cached_turn = cached.get("turn", 0)
        current_turn = tool_context.state.get("turns_used", 0)

        if current_turn - cached_turn <= TOOL_CACHE_TTL_TURNS:
            # Serve from cache — the real tool function is never called.
            return {**cached_result, "_served_from_cache": True}

    # Cache miss — return None to let the tool run. After execution, the
    # after_tool_callback will populate the cache.
    return None


# ---------------------------------------------------------------------------
# 5. after_tool_callback — Audit Log + Populate Cache
# ---------------------------------------------------------------------------
def audit_and_cache_callback(
    tool: BaseTool,
    args: dict,
    tool_context: ToolContext,
    tool_response: dict,
) -> dict | None:
    """
    Runs AFTER every tool execution (only when not served from cache).

    Does two things:
    1. Appends an audit log entry to session state for compliance tracing.
    2. Stores the result in the temp: cache so before_tool_callback can serve it.

    Returning None keeps the original tool_response unchanged.
    """
    state = tool_context.state

    # --- Audit log ---
    log = state.get("tool_audit_log", [])
    log.append({
        "tool": tool.name,
        "args": args,
        "status": tool_response.get("status", "unknown"),
    })
    # Cap the log to avoid unbounded growth in long sessions.
    state["tool_audit_log"] = log[-20:]

    # --- Populate cache (only if result was successful) ---
    if tool_response.get("status") != "error":
        cache_key = f"temp:cache:{tool.name}:{sorted(args.items())}"
        state[cache_key] = {
            "result": tool_response,
            "turn": state.get("turns_used", 0),
        }

    return None  # do not alter the tool's result


# ---------------------------------------------------------------------------
# 6. after_agent_callback — Increment Turn Counter
# ---------------------------------------------------------------------------
async def increment_turn_counter(callback_context: CallbackContext) -> genai_types.Content | None:
    """
    Runs ONCE after every successful agent turn.
    Increments the turn counter that the rate_limit_callback reads.
    """
    state = callback_context.state
    state["turns_used"] = state.get("turns_used", 0) + 1
    # Returning None keeps the agent's output unchanged.
    return None


# ---------------------------------------------------------------------------
# Tool Functions — simple support agent tools
# ---------------------------------------------------------------------------

def get_order_status(order_id: str, tool_context: ToolContext) -> dict:
    """Look up the current status of a customer order.

    Args:
        order_id: The order identifier to look up.
    """
    # Simulated order database lookup.
    fake_orders = {
        "ORD-001": {"status": "shipped", "estimated_delivery": "2026-06-12"},
        "ORD-002": {"status": "processing", "estimated_delivery": "2026-06-15"},
        "ORD-003": {"status": "delivered", "estimated_delivery": "2026-06-01"},
    }
    order = fake_orders.get(order_id.upper())
    if not order:
        return {"status": "error", "message": f"Order {order_id} not found."}
    return {"status": "success", "order_id": order_id, **order}


def get_product_info(product_id: str) -> dict:
    """Retrieve product details including price and availability.

    Args:
        product_id: The product identifier to look up.
    """
    fake_products = {
        "PROD-A1": {"name": "Widget Pro", "price": 49.99, "in_stock": True},
        "PROD-B2": {"name": "Gadget Max", "price": 129.99, "in_stock": False},
        "PROD-C3": {"name": "Super Tool", "price": 29.99, "in_stock": True},
    }
    product = fake_products.get(product_id.upper())
    if not product:
        return {"status": "error", "message": f"Product {product_id} not found."}
    return {"status": "success", "product_id": product_id, **product}


def set_user_tier(tier: str, tool_context: ToolContext) -> dict:
    """Set the user support tier to see dynamic context injection in action.

    Args:
        tier: One of 'standard', 'premium', or 'trial'.
    """
    valid = ["standard", "premium", "trial"]
    if tier not in valid:
        return {"status": "error", "message": f"Invalid tier. Choose from: {valid}"}
    tool_context.state["user:tier"] = tier
    return {"status": "updated", "tier": tier,
            "note": "The before_model_callback will now inject tier-specific context into every LLM call."}


# ---------------------------------------------------------------------------
# Agent Assembly — wiring all six callbacks
# ---------------------------------------------------------------------------
root_agent = Agent(
    model="gemini-2.5-flash",
    name="customer_support_agent",
    description="Customer support agent with a full six-callback stack for rate limiting, guardrails, caching, and auditing.",
    instruction="""
    You are a friendly customer support agent.
    You can look up order statuses, retrieve product information, and set user tier.

    IMPORTANT: You have a session limit of {turns_used}/{app:total_orders_processed} turns.
    Current estimated tokens this session: {session_estimated_output_tokens}.

    Always be concise and helpful.
    """,
    tools=[get_order_status, get_product_info, set_user_tier],
    # Six callbacks wired in — each targeting a different lifecycle hook.
    before_agent_callback=rate_limit_callback,
    after_agent_callback=increment_turn_counter,
    before_model_callback=guardrail_and_inject_callback,
    after_model_callback=enrich_response_callback,
    before_tool_callback=tool_cache_callback,
    after_tool_callback=audit_and_cache_callback,
)
