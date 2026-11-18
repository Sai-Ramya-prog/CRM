"""
Gemini chat sessions for the CRM assistant.

A session is built per logged-in person, with the tool set and system prompt
that match who they are. The caller's JWT is baked into the tools, so the
backend's own role checks decide what the agent can actually do.
"""

import os
import threading

from dotenv import load_dotenv
from google import genai

from .crm_tools import build_customer_tools, build_staff_tools

# Load ai-agent/.env (the backend's own .env is loaded separately by main.py)
_env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(dotenv_path=_env_path)

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").removeprefix("models/")

_PROMPT_DIR = os.path.join(os.path.dirname(__file__), "..", "prompts")


def _load_prompt(filename: str) -> str:
    with open(os.path.join(_PROMPT_DIR, filename), "r", encoding="utf-8") as fh:
        return fh.read()


# One client for the whole process.
#
# This must NOT be created per call. A Client created as a local variable is
# garbage-collected once the function returns, which closes its HTTP transport.
# The chat object outlives it, so the next send_message() fails with
# "Cannot send a request, as the client has been closed."
_CLIENT: genai.Client | None = None
_CLIENT_LOCK = threading.Lock()


def _client() -> genai.Client:
    global _CLIENT
    if _CLIENT is None:
        with _CLIENT_LOCK:
            if _CLIENT is None:
                if not API_KEY or API_KEY == "your_api_key_here":
                    raise ValueError(
                        "Missing GEMINI_API_KEY. Add it to ai-agent/.env (local) "
                        "or to the service's environment variables (Render)."
                    )
                _CLIENT = genai.Client(api_key=API_KEY)
    return _CLIENT


def create_staff_session(token: str, name: str, role: str):
    """Build a chat session for a staff member, scoped to their own token."""
    system_instruction = _load_prompt("staff_prompt.txt").format(name=name, role=role)
    return _client().chats.create(
        model=MODEL_NAME,
        config={
            "tools": build_staff_tools(token),
            "system_instruction": system_instruction,
        },
    )


def create_customer_session(token: str, name: str):
    """Build a chat session for a customer, scoped to their own token."""
    system_instruction = _load_prompt("customer_prompt.txt").format(name=name)
    return _client().chats.create(
        model=MODEL_NAME,
        config={
            "tools": build_customer_tools(token),
            "system_instruction": system_instruction,
        },
    )
