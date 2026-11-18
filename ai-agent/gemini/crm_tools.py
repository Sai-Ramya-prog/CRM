"""
CRM tools for the Gemini agent.

Design note
-----------
The agent does NOT have permissions of its own. Every tool calls the backend
REST API carrying the *caller's* JWT, so the existing FastAPI dependencies
(`require_admin`, `require_lead_or_admin`, `get_current_staff`,
`get_current_customer`) decide what is allowed. An EMPLOYEE's agent cannot
assign a ticket because `/tickets/{id}/assign` returns 403 for them.

This means permission logic lives in exactly one place: the backend.

Tools are built per request by `build_staff_tools(token)` /
`build_customer_tools(token)`, which return plain functions with the token
captured in a closure. Gemini reads their names, type hints and docstrings.
"""

import json
import os

import requests

# Where the tools call back into. The agent runs inside the backend process,
# so this is normally the server calling itself over loopback.
BACKEND_URL = (
    os.getenv("INTERNAL_BACKEND_URL")
    or os.getenv("BACKEND_API_URL")
    or os.getenv("BACKEND_URL")
    or f"http://127.0.0.1:{os.getenv('PORT', '8000')}"
).rstrip("/")

TIMEOUT = 15


# ── HTTP helpers ────────────────────────────────────────────────────────────

def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _fmt(resp: requests.Response) -> str:
    """Turn a response into text the model can read, including failures."""
    if resp.status_code == 401:
        return "Not authorised - the session may have expired. Ask the user to log in again."
    if resp.status_code == 403:
        return (
            "Permission denied. Your role is not allowed to do this. "
            "Tell the user plainly that they do not have permission for this action."
        )
    if resp.status_code == 404:
        return "Not found - no record with that id."
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail")
        except Exception:
            detail = resp.text[:300]
        return f"The request failed ({resp.status_code}): {detail}"
    if resp.status_code == 204 or not resp.text:
        return "Done."
    try:
        return json.dumps(resp.json(), indent=2, default=str)
    except Exception:
        return resp.text[:2000]


def _call(method: str, path: str, token: str, params=None, body=None) -> str:
    url = f"{BACKEND_URL}{path}"
    try:
        resp = requests.request(
            method, url, headers=_headers(token), params=params, json=body, timeout=TIMEOUT
        )
    except requests.exceptions.RequestException as exc:
        return f"Could not reach the CRM API: {exc}"
    return _fmt(resp)


NEEDS_CONFIRM = (
    "This action is destructive and has NOT been carried out. "
    "Describe exactly what will happen, ask the user to confirm, and only call "
    "this tool again with confirm=True after they clearly say yes."
)


# ── Staff tools (ADMIN / LEAD / EMPLOYEE) ───────────────────────────────────

def build_staff_tools(token: str) -> list:
    """Return the staff tool set, bound to this staff member's token."""

    def get_dashboard_stats() -> str:
        """Get CRM dashboard statistics for the logged-in staff member.

        The numbers are scoped by role automatically: an admin sees global
        figures, a lead sees their team, an employee sees their own.
        """
        return _call("GET", "/dashboard", token)

    def list_tickets(status: str = "", unassigned: bool = False) -> str:
        """List support tickets visible to the logged-in staff member.

        Args:
            status: Optional filter, e.g. 'OPEN' or 'RESOLVED'. Empty means all.
            unassigned: True to show only tickets with no agent assigned yet.
        """
        params = {}
        if status:
            params["status"] = status
        if unassigned:
            params["unassigned"] = True
        return _call("GET", "/tickets", token, params=params)

    def get_ticket_messages(ticket_id: int) -> str:
        """Read the full chat history of one support ticket.

        Args:
            ticket_id: The id of the ticket.
        """
        return _call("GET", f"/tickets/{ticket_id}/messages", token)

    def assign_ticket(ticket_id: int, employee_id: int) -> str:
        """Assign a ticket to an employee. Only a LEAD or ADMIN may do this.

        A lead may only assign to members of their own team. Call list_staff
        first if you need the employee's id.

        Args:
            ticket_id: The ticket to assign.
            employee_id: The staff id of the employee who should handle it.
        """
        return _call(
            "POST", f"/tickets/{ticket_id}/assign", token, body={"employee_id": employee_id}
        )

    def resolve_ticket(ticket_id: int) -> str:
        """Mark a ticket as resolved. This permanently locks its chat to read-only.

        Args:
            ticket_id: The ticket to resolve.
        """
        return _call("POST", f"/tickets/{ticket_id}/resolve", token)

    def list_staff() -> str:
        """List staff members visible to the logged-in user, with ids, names and roles."""
        return _call("GET", "/staff", token)

    def get_staff_member(user_id: int) -> str:
        """Get details and performance figures for one staff member.

        Args:
            user_id: The staff member's id.
        """
        return _call("GET", f"/staff/{user_id}", token)

    def list_customers() -> str:
        """List customers visible to the logged-in staff member."""
        return _call("GET", "/customers", token)

    def get_customer(customer_id: int) -> str:
        """Get one customer with their orders and tickets.

        Args:
            customer_id: The customer's id.
        """
        return _call("GET", f"/customers/{customer_id}", token)

    def update_order_status(order_id: int, status: str) -> str:
        """Move an order to a new status.

        Allowed moves: PLACED -> SHIPPED or CANCELLED, SHIPPED -> DELIVERED.
        DELIVERED and CANCELLED are final.

        Args:
            order_id: The order to update.
            status: The new status.
        """
        return _call(
            "PATCH", f"/orders/{order_id}/status", token, body={"status": status.upper().strip()}
        )

    def list_announcements() -> str:
        """List all company announcements."""
        return _call("GET", "/announcements", token)

    def create_announcement(title: str, content: str) -> str:
        """Publish a new announcement. ADMIN only.

        Args:
            title: Short headline.
            content: The announcement body.
        """
        return _call(
            "POST", "/announcements", token, body={"title": title, "content": content}
        )

    def update_announcement(announcement_id: int, title: str, content: str) -> str:
        """Replace the title and content of an announcement. ADMIN only.

        Args:
            announcement_id: The announcement to change.
            title: The new headline.
            content: The new body.
        """
        return _call(
            "PUT",
            f"/announcements/{announcement_id}",
            token,
            body={"title": title, "content": content},
        )

    def delete_announcement(announcement_id: int, confirm: bool = False) -> str:
        """Delete an announcement permanently. ADMIN only. Needs confirm=True.

        Args:
            announcement_id: The announcement to delete.
            confirm: Must be True. Ask the user first; never set this yourself.
        """
        if not confirm:
            return NEEDS_CONFIRM
        return _call("DELETE", f"/announcements/{announcement_id}", token)

    def list_deals() -> str:
        """List sales deals recorded in the CRM."""
        return _call("GET", "/deals/", token)

    return [
        get_dashboard_stats,
        list_tickets,
        get_ticket_messages,
        assign_ticket,
        resolve_ticket,
        list_staff,
        get_staff_member,
        list_customers,
        get_customer,
        update_order_status,
        list_announcements,
        create_announcement,
        update_announcement,
        delete_announcement,
        list_deals,
    ]


# ── Customer tools ──────────────────────────────────────────────────────────

def build_customer_tools(token: str) -> list:
    """Return the customer tool set, bound to this customer's token."""

    def list_products() -> str:
        """List all products available in the shop, with ids and prices."""
        return _call("GET", "/products", token)

    def get_product(product_id: int) -> str:
        """Get details of one product.

        Args:
            product_id: The product's id.
        """
        return _call("GET", f"/products/{product_id}", token)

    def my_account() -> str:
        """Get the logged-in customer's own profile details."""
        return _call("GET", "/customer/me", token)

    def my_orders() -> str:
        """List the logged-in customer's own orders, with ids and statuses."""
        return _call("GET", "/orders/me", token)

    def place_order(product_id: int, quantity: int = 1, confirm: bool = False) -> str:
        """Book an order for the logged-in customer. Needs confirm=True.

        Args:
            product_id: The product to order. Use list_products to find it.
            quantity: How many, between 1 and 10.
            confirm: Must be True. Show the product and quantity and ask the
                user to confirm first; never set this yourself.
        """
        if not confirm:
            return NEEDS_CONFIRM
        return _call(
            "POST", "/orders", token, body={"product_id": product_id, "quantity": quantity}
        )

    def cancel_order(order_id: int, confirm: bool = False) -> str:
        """Cancel one of the customer's own orders. Needs confirm=True.

        Only an order still in PLACED status can be cancelled.

        Args:
            order_id: The order to cancel.
            confirm: Must be True. Ask the user first; never set this yourself.
        """
        if not confirm:
            return NEEDS_CONFIRM
        return _call("POST", f"/orders/{order_id}/cancel", token)

    def my_tickets() -> str:
        """List the logged-in customer's own support tickets and their statuses."""
        return _call("GET", "/customer/tickets", token)

    def open_ticket(order_id: int, category: str, message: str, subject: str = "") -> str:
        """Open a support ticket about one of the customer's orders.

        Only one open ticket per order is allowed at a time.

        Args:
            order_id: The order the problem is about.
            category: One of DAMAGED, LATE_DELIVERY, WRONG_ITEM, CANCEL_REFUND, OTHER.
            message: What the customer wants to say, in their own words.
            subject: Optional short title.
        """
        body = {
            "order_id": order_id,
            "category": category.upper().strip(),
            "message": message,
        }
        if subject:
            body["subject"] = subject
        return _call("POST", "/customer/tickets", token, body=body)

    def get_my_ticket_messages(ticket_id: int) -> str:
        """Read the chat history of one of the customer's own tickets.

        Args:
            ticket_id: The ticket's id.
        """
        return _call("GET", f"/customer/tickets/{ticket_id}/messages", token)

    def rate_ticket(ticket_id: int, rating: int) -> str:
        """Give a 1-5 star rating to one of the customer's resolved tickets.

        A ticket can only be rated once, and only after it is resolved.

        Args:
            ticket_id: The ticket to rate.
            rating: A whole number from 1 to 5.
        """
        return _call("POST", f"/customer/tickets/{ticket_id}/rate", token, body={"rating": rating})

    return [
        list_products,
        get_product,
        my_account,
        my_orders,
        place_order,
        cancel_order,
        my_tickets,
        open_ticket,
        get_my_ticket_messages,
        rate_ticket,
    ]
