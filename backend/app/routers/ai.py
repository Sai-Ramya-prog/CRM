import os
import sys
import threading
import time

from fastapi import APIRouter, Depends, Header, HTTPException

from app.auth.dependencies import get_current_actor
from app.models.customer import Customer
from app.models.user import User
from app.schemas.ai import AIChatRequest, AIChatResponse

router = APIRouter(prefix="/ai", tags=["AI"])

# The agent code lives outside the backend package.
_AI_AGENT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "ai-agent")
)
if _AI_AGENT_DIR not in sys.path:
    sys.path.append(_AI_AGENT_DIR)


# ── Per-person chat sessions ────────────────────────────────────────────────
#
# One session per logged-in person, not one global session for everybody.
# Each entry holds the token the session was built with: when someone logs in
# again their token changes, so the session is rebuilt and the new token is
# what the tools use.

_SESSIONS: dict[str, dict] = {}
_LOCK = threading.Lock()

SESSION_IDLE_SECONDS = 60 * 60   # drop sessions untouched for an hour
MAX_HISTORY_MESSAGES = 20        # keep the last 10 exchanges


def _prune_locked() -> None:
    cutoff = time.time() - SESSION_IDLE_SECONDS
    for key in [k for k, v in _SESSIONS.items() if v["touched"] < cutoff]:
        _SESSIONS.pop(key, None)


def _build_session(actor, token: str):
    from gemini.client import create_customer_session, create_staff_session

    if isinstance(actor, Customer):
        return create_customer_session(token=token, name=actor.name)
    return create_staff_session(token=token, name=actor.name, role=actor.role)


def _get_session(actor, token: str):
    key = f"{'customer' if isinstance(actor, Customer) else 'staff'}:{actor.id}"
    with _LOCK:
        _prune_locked()
        entry = _SESSIONS.get(key)
        if entry and entry["token"] == token:
            entry["touched"] = time.time()
            return entry["chat"]

    chat = _build_session(actor, token)
    with _LOCK:
        _SESSIONS[key] = {"chat": chat, "token": token, "touched": time.time()}
    return chat


def _reset_session(actor) -> None:
    key = f"{'customer' if isinstance(actor, Customer) else 'staff'}:{actor.id}"
    with _LOCK:
        _SESSIONS.pop(key, None)


def _trim_history(chat) -> None:
    """Keep the context from growing without bound."""
    try:
        history = chat.get_history()
        if len(history) > MAX_HISTORY_MESSAGES:
            del history[:-MAX_HISTORY_MESSAGES]
    except Exception:
        pass


def _extract_text(response) -> str:
    try:
        if response.text:
            return response.text.strip()
    except Exception:
        pass

    parts_text = []
    for candidate in getattr(response, "candidates", []) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            text = getattr(part, "text", "")
            if text:
                parts_text.append(text)
    return " ".join(parts_text).strip()


def _bearer_token(authorization: str) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return token


# ── Endpoints ───────────────────────────────────────────────────────────────

@router.post("/chat", response_model=AIChatResponse)
def chat_with_ai(
    request: AIChatRequest,
    actor: User | Customer = Depends(get_current_actor),
    authorization: str = Header(..., alias="Authorization"),
):
    """
    Send a message to the CRM assistant.

    Requires a staff or customer token. The agent acts as the caller: every
    tool call carries this same token, so the backend's own role checks decide
    what the agent is allowed to do.
    """
    token = _bearer_token(authorization)

    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    chat = _get_session(actor, token)

    try:
        response = chat.send_message(request.message)
    except Exception as first_error:
        # A stale session can poison the history; rebuild once and retry.
        print(f"/ai/chat error, rebuilding session: {first_error}")
        _reset_session(actor)
        try:
            chat = _get_session(actor, token)
            response = chat.send_message(request.message)
        except Exception as retry_error:
            print(f"/ai/chat failed after retry: {retry_error}")
            raise HTTPException(
                status_code=503,
                detail=f"The assistant is unavailable right now: {retry_error}"[:300],
            )

    _trim_history(chat)

    reply = _extract_text(response) or "Done."
    return AIChatResponse(response=reply, actions_taken=[])


@router.post("/reset")
def reset_ai_chat(actor: User | Customer = Depends(get_current_actor)):
    """Clear the caller's conversation history and start fresh."""
    _reset_session(actor)
    return {"status": "ok"}
