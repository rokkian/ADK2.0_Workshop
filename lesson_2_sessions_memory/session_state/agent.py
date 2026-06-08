"""
Phase 2 - Example 1: Session State & Agent Context
===================================================

This module teaches how agents read and write state within a conversation.
It builds a shopping cart assistant that demonstrates all four state scopes.

ADK State Prefix Reference:
----------------------------
  state["key"]             Session scope  — lives for this conversation only
  state["user:key"]        User scope     — shared across all sessions for this user
                                            (requires a persistent SessionService to truly persist)
  state["app:key"]         App scope      — shared across ALL users of the application
  state["temp:key"]        Temp scope     — discarded at the end of the current LLM invocation

Why Each Scope Matters:
------------------------
- Session scope   → cart contents: only relevant while shopping in this conversation.
- User scope      → preferred currency: personal setting the user configured once.
- App scope       → order counter: a global metric spanning every user.
- Temp scope      → intermediate calculation: ephemeral data that should never be persisted.

Instruction Templating:
------------------------
ADK automatically injects state values into instructions at runtime via {key} placeholders.
This works for all scopes, including prefixed keys like {user:preferred_currency}.
The value is resolved BEFORE the LLM sees the system prompt on each turn.

IMPORTANT — Persistence vs. InMemorySessionService:
----------------------------------------------------
`adk web` (the dev server) uses InMemorySessionService by default.
With this service, user: and app: state behaves just like session state — it is
lost on server restart. To get true cross-session persistence you must wire a
DatabaseSessionService or VertexAiSessionService into your Runner.
See phase_2/persistence/agent.py for a full demonstration of this.
"""

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools import ToolContext
from google.genai import types as genai_types


# ---------------------------------------------------------------------------
# 1. State Initialization — before_agent_callback
# ---------------------------------------------------------------------------
async def initialize_state(callback_context: CallbackContext) -> None:
    """
    Runs before EVERY agent turn. Safe-initializes all state keys used by this
    agent so that tools and instruction templates never hit a KeyError.

    Pattern: always guard with `if "key" not in state` to avoid resetting
    values that were written in a previous turn of this same session.

    Returning None (implicit) lets the agent continue normally.
    Returning a types.Content would SKIP the LLM call and reply immediately.
    """
    state = callback_context.state

    # Session-scoped: cart lives only within this conversation thread.
    if "cart_items" not in state:
        state["cart_items"] = []
    if "order_total" not in state:
        state["order_total"] = 0.0

    # User-scoped: personal settings that persist across sessions (with a
    # persistent SessionService). Colon is valid in state keys AND in templates.
    if "user:preferred_currency" not in state:
        state["user:preferred_currency"] = "USD"
    if "user:display_name" not in state:
        state["user:display_name"] = "Guest"

    # App-scoped: a global counter shared across all users and sessions.
    if "app:total_orders_processed" not in state:
        state["app:total_orders_processed"] = 0


# ---------------------------------------------------------------------------
# 2. Tool Functions — Reading and Writing State via ToolContext
# ---------------------------------------------------------------------------

def add_to_cart(product_name: str, price: float, tool_context: ToolContext) -> dict:
    """Add a product to the shopping cart.

    Args:
        product_name: The name of the product to add.
        price: The numeric price of the product.
    """
    # ToolContext.state exposes the same session state dict, fully writable.
    cart = tool_context.state.get("cart_items", [])
    currency = tool_context.state.get("user:preferred_currency", "USD")

    item = {"name": product_name, "price": price}
    cart.append(item)

    tool_context.state["cart_items"] = cart
    tool_context.state["order_total"] = round(sum(i["price"] for i in cart), 2)

    # temp: scope — only survives the current invocation; never persisted.
    # Useful for values that should be visible to other tools called in the
    # same turn but must not leak into the next turn.
    tool_context.state["temp:last_added_item"] = product_name

    return {
        "status": "added",
        "product": product_name,
        "price": f"{price} {currency}",
        "cart_size": len(cart),
        "new_total": f"{tool_context.state['order_total']} {currency}",
    }


def remove_from_cart(product_name: str, tool_context: ToolContext) -> dict:
    """Remove a product from the cart by name (first match).

    Args:
        product_name: The exact name of the product to remove.
    """
    cart = tool_context.state.get("cart_items", [])
    original_size = len(cart)

    cart = [item for item in cart if item["name"].lower() != product_name.lower()]
    tool_context.state["cart_items"] = cart
    tool_context.state["order_total"] = round(sum(i["price"] for i in cart), 2)

    removed = original_size - len(cart)
    currency = tool_context.state.get("user:preferred_currency", "USD")

    return {
        "status": "removed" if removed > 0 else "not_found",
        "items_removed": removed,
        "new_total": f"{tool_context.state['order_total']} {currency}",
    }


def view_cart(tool_context: ToolContext) -> dict:
    """View all items currently in the shopping cart."""
    cart = tool_context.state.get("cart_items", [])
    total = tool_context.state.get("order_total", 0.0)
    currency = tool_context.state.get("user:preferred_currency", "USD")

    # Reading app: scope from a tool — illustrates cross-user shared state.
    global_orders = tool_context.state.get("app:total_orders_processed", 0)

    return {
        "items": cart,
        "total": f"{total:.2f} {currency}",
        "item_count": len(cart),
        "app_global_orders_processed": global_orders,
    }


def checkout(tool_context: ToolContext) -> dict:
    """Finalise the purchase and clear the cart.

    Demonstrates writing to app: scope (incrementing a global counter) and
    resetting session-scoped state without touching user: preferences.
    """
    cart = tool_context.state.get("cart_items", [])
    if not cart:
        return {"status": "error", "message": "Cart is empty."}

    total = tool_context.state.get("order_total", 0.0)
    currency = tool_context.state.get("user:preferred_currency", "USD")
    display_name = tool_context.state.get("user:display_name", "Guest")

    # Increment app-wide counter — visible to all users after this point.
    current_count = tool_context.state.get("app:total_orders_processed", 0)
    tool_context.state["app:total_orders_processed"] = current_count + 1

    # Reset session state after purchase — user preferences are untouched.
    tool_context.state["cart_items"] = []
    tool_context.state["order_total"] = 0.0

    return {
        "status": "success",
        "message": f"Order placed for {display_name}!",
        "items_purchased": len(cart),
        "amount_charged": f"{total:.2f} {currency}",
        "global_order_number": current_count + 1,
    }


def set_currency(currency_code: str, tool_context: ToolContext) -> dict:
    """Set the preferred currency. This preference persists across sessions.

    Args:
        currency_code: ISO 4217 code, e.g. USD, EUR, GBP, JPY.
    """
    supported = ["USD", "EUR", "GBP", "JPY", "CAD", "AUD", "CHF"]
    code = currency_code.strip().upper()
    if code not in supported:
        return {"status": "error", "message": f"Unsupported currency. Choose from: {supported}"}

    # Writing to user: scope — persists with a DatabaseSessionService or VertexAiSessionService.
    tool_context.state["user:preferred_currency"] = code
    return {
        "status": "updated",
        "currency": code,
        "note": "Preference stored. With a persistent session service this survives restarts.",
    }


def set_display_name(name: str, tool_context: ToolContext) -> dict:
    """Set your display name. This setting persists across sessions.

    Args:
        name: The name to display in greetings.
    """
    tool_context.state["user:display_name"] = name.strip()
    return {"status": "updated", "name": name.strip()}


# ---------------------------------------------------------------------------
# 3. Agent — Instruction Templating and output_key
# ---------------------------------------------------------------------------
root_agent = Agent(
    model="gemini-2.5-flash",
    name="shopping_cart_agent",
    description="A shopping cart assistant demonstrating all ADK state scopes.",
    instruction="""
    You are a helpful shopping assistant for {user:display_name}.
    The user's preferred currency is: {user:preferred_currency}
    Current cart contents: {cart_items}
    Current cart total: {order_total} {user:preferred_currency}
    Global orders processed (app-wide): {app:total_orders_processed}

    You can:
    - Add items to the cart (ask for product name and price if not given)
    - Remove items from the cart
    - View the current cart
    - Process checkout
    - Change the preferred currency (persists across sessions)
    - Set a display name (persists across sessions)

    Always confirm the updated cart total after any modification.
    Be concise and friendly.
    """,
    tools=[add_to_cart, remove_from_cart, view_cart, checkout, set_currency, set_display_name],
    # output_key: after every turn, the agent's final text is written into state["last_response"].
    # Other agents in a multi-agent pipeline could then read it from state.
    output_key="last_response",
    # before_agent_callback: guarantees state is initialized before any turn.
    before_agent_callback=initialize_state,
)
