"""
OpenAI provider for the CRM assistant.

Same design as the Gemini provider: a session is built per logged-in person,
with the tool set and system prompt that match who they are, and every tool
carries that person's JWT so the backend decides what is allowed.

Two differences from Gemini:

1. The OpenAI SDK does not run the tool loop for you, so this module runs it:
   call the model, execute any tools it asked for, send the results back, and
   repeat until it answers in words.
2. Tools are described as JSON schemas rather than Python callables. The
   schemas here are generated from the same functions in crm_tools.py by
   reading their signatures and docstrings, so there is one definition of each
   tool, not two.
"""

import inspect
import json
import os
import re
import threading
from types import SimpleNamespace

from dotenv import load_dotenv
from openai import OpenAI

from gemini.crm_tools import build_customer_tools, build_staff_tools

_HERE = os.path.dirname(__file__)
load_dotenv(dotenv_path=os.path.join(_HERE, ".env"), override=True)

API_KEY = os.getenv("OPENAI_API_KEY")
MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

# How many times the model may call tools before it has to answer in words.
MAX_TOOL_ROUNDS = 6

# Keep the system prompt plus this many later messages.
MAX_HISTORY = 30

_PROMPT_DIR = os.path.join(_HERE, "prompts")

_CLIENT: OpenAI | None = None
_CLIENT_LOCK = threading.Lock()


def _client() -> OpenAI:
    """One client for the process - see the note in gemini/client.py."""
    global _CLIENT
    if _CLIENT is None:
        with _CLIENT_LOCK:
            if _CLIENT is None:
                if not API_KEY:
                    raise ValueError(
                        "Missing OPENAI_API_KEY. Add it to ai-agent/.env (local) "
                        "or to the service's environment variables (Render)."
                    )
                _CLIENT = OpenAI(api_key=API_KEY)
    return _CLIENT


def _load_prompt(filename: str) -> str:
    with open(os.path.join(_PROMPT_DIR, filename), "r", encoding="utf-8") as fh:
        return fh.read()


# ── Turning crm_tools functions into OpenAI tool schemas ────────────────────

_PY_TO_JSON = {int: "integer", float: "number", bool: "boolean", str: "string"}


def _split_docstring(doc: str) -> tuple[str, dict]:
    """Return (summary, {param_name: description}) from a Google-style docstring."""
    doc = inspect.cleandoc(doc or "")
    head, _, args_block = doc.partition("Args:")
    summary = head.strip()

    descriptions: dict[str, str] = {}
    current: str | None = None
    for line in args_block.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = re.match(r"^(\w+)\s*:\s*(.*)$", stripped)
        if match:
            current = match.group(1)
            descriptions[current] = match.group(2).strip()
        elif current:
            descriptions[current] += " " + stripped
    return summary, descriptions


def _schema_for(func) -> dict:
    summary, param_docs = _split_docstring(func.__doc__)
    signature = inspect.signature(func)

    properties: dict[str, dict] = {}
    required: list[str] = []

    for name, param in signature.parameters.items():
        json_type = _PY_TO_JSON.get(param.annotation, "string")
        properties[name] = {
            "type": json_type,
            "description": param_docs.get(name, name.replace("_", " ")),
        }
        if param.default is inspect.Parameter.empty:
            required.append(name)

    return {
        "type": "function",
        "function": {
            "name": func.__name__,
            "description": summary,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


# ── The session ─────────────────────────────────────────────────────────────

class OpenAIChatSession:
    """Mirrors the small part of the Gemini chat interface that ai.py uses."""

    def __init__(self, tools: list, system_instruction: str):
        self._registry = {func.__name__: func for func in tools}
        self._schemas = [_schema_for(func) for func in tools]
        self._messages = [{"role": "system", "content": system_instruction}]

    # ai.py calls this to cap context growth.
    def get_history(self) -> list:
        return self._messages

    def _trim(self) -> None:
        """Drop old turns, never splitting an assistant/tool pair."""
        if len(self._messages) <= MAX_HISTORY + 1:
            return
        system, rest = self._messages[0], self._messages[1:]
        rest = rest[-MAX_HISTORY:]
        # A 'tool' message is only valid right after the assistant message that
        # requested it, so discard any that lost their partner in the cut.
        while rest and rest[0].get("role") == "tool":
            rest.pop(0)
        self._messages = [system] + rest

    def send_message(self, text: str):
        self._messages.append({"role": "user", "content": text})

        for _ in range(MAX_TOOL_ROUNDS):
            completion = _client().chat.completions.create(
                model=MODEL_NAME,
                messages=self._messages,
                tools=self._schemas,
                tool_choice="auto",
            )
            message = completion.choices[0].message

            assistant_entry: dict = {"role": "assistant", "content": message.content}
            if message.tool_calls:
                assistant_entry["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        },
                    }
                    for call in message.tool_calls
                ]
            self._messages.append(assistant_entry)

            if not message.tool_calls:
                self._trim()
                return SimpleNamespace(text=(message.content or "").strip())

            for call in message.tool_calls:
                self._messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": self._run_tool(call),
                    }
                )

        self._trim()
        return SimpleNamespace(
            text="That needed too many steps. Could you ask for one thing at a time?"
        )

    def _run_tool(self, call) -> str:
        name = call.function.name
        func = self._registry.get(name)
        if func is None:
            return f"No such tool: {name}"
        try:
            arguments = json.loads(call.function.arguments or "{}")
        except json.JSONDecodeError:
            return "Could not read the arguments for that tool call."
        try:
            return str(func(**arguments))
        except TypeError as exc:
            return f"Wrong arguments for {name}: {exc}"
        except Exception as exc:  # a tool failing must not kill the turn
            print(f"[openai] tool {name} raised: {exc}")
            return f"The tool {name} failed: {exc}"


# ── Entry points, matching gemini.client ────────────────────────────────────

def create_staff_session(token: str, name: str, role: str) -> OpenAIChatSession:
    prompt = _load_prompt("staff_prompt.txt").format(name=name, role=role)
    return OpenAIChatSession(build_staff_tools(token), prompt)


def create_customer_session(token: str, name: str) -> OpenAIChatSession:
    prompt = _load_prompt("customer_prompt.txt").format(name=name)
    return OpenAIChatSession(build_customer_tools(token), prompt)


print(f"[ai-agent] OpenAI provider ready, model: {MODEL_NAME!r}")
