"""
Adapter for any OpenAI-compatible chat completions API (Groq, OpenRouter, Ollama, ...).

AgentBase keeps its history in Gemini's shape: {"role": "user"|"model", "parts": [...]}
with text, function_call and function_response parts. This module converts that
history to OpenAI messages on each request and wraps the reply in the same shape the
Gemini SDK returns, so the tool loop in base.py runs unchanged for both providers.
"""

import json
from types import SimpleNamespace

import httpx

FINISH_REASONS = {
    "stop": "STOP",
    "tool_calls": "STOP",
    "length": "MAX_TOKENS",
    "content_filter": "SAFETY",
}


def _get(obj, key):
    """Read a field from a dict part or an SDK/namespace part."""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def to_openai_tools(declarations: list[dict]) -> list[dict]:
    """Gemini function declarations -> OpenAI tool definitions."""
    return [
        {
            "type": "function",
            "function": {
                "name": d["name"],
                "description": d.get("description", ""),
                "parameters": d.get("parameters", {"type": "object", "properties": {}}),
            },
        }
        for d in declarations
    ]


def to_openai_messages(system_prompt: str, contents: list) -> list[dict]:
    """
    Gemini-shaped history -> OpenAI messages.

    Gemini pairs tool results with calls by position, OpenAI by id. The loop in
    base.py appends one function_response per function_call, in call order, in the
    user turn right after the model turn, so ids are generated per model turn and
    matched by position.
    """
    messages = [{"role": "system", "content": system_prompt}]
    pending_ids: list[str] = []
    turn = 0
    for content in contents:
        role = _get(content, "role")
        parts = _get(content, "parts") or []
        texts = [t for p in parts if (t := _get(p, "text"))]
        calls = [c for p in parts if (c := _get(p, "function_call"))]
        results = [r for p in parts if (r := _get(p, "function_response"))]

        if role == "model":
            message = {"role": "assistant", "content": "\n".join(texts) or None}
            if calls:
                turn += 1
                pending_ids = [f"call_{turn}_{i}" for i in range(len(calls))]
                message["tool_calls"] = [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": _get(call, "name"),
                            "arguments": json.dumps(dict(_get(call, "args") or {})),
                        },
                    }
                    for call_id, call in zip(pending_ids, calls)
                ]
            if message["content"] is not None or calls:
                messages.append(message)
            continue

        for i, result in enumerate(results):
            call_id = pending_ids[i] if i < len(pending_ids) else f"call_{turn}_{i}"
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": json.dumps(_get(result, "response"), default=str),
                }
            )
        if texts:
            messages.append({"role": "user", "content": "\n".join(texts)})
    return messages


def _response(parts: list, finish_reason: str, prompt_tokens=0, completion_tokens=0):
    """Wrap a reply in the attributes base.py reads from a Gemini response."""
    return SimpleNamespace(
        candidates=[
            SimpleNamespace(
                finish_reason=finish_reason,
                content=SimpleNamespace(role="model", parts=parts) if parts else None,
            )
        ],
        usage_metadata=SimpleNamespace(
            prompt_token_count=prompt_tokens,
            candidates_token_count=completion_tokens,
        ),
        function_calls=None,
    )


def from_openai_response(data: dict):
    """OpenAI chat completion JSON -> Gemini-shaped response."""
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    parts = []
    if message.get("content"):
        parts.append(SimpleNamespace(text=message["content"], function_call=None))
    for call in message.get("tool_calls") or []:
        fn = call.get("function") or {}
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            return _response([], "MALFORMED_FUNCTION_CALL")
        if not isinstance(args, dict):
            return _response([], "MALFORMED_FUNCTION_CALL")
        parts.append(
            SimpleNamespace(
                text=None,
                function_call=SimpleNamespace(name=fn.get("name"), args=args),
            )
        )
    usage = data.get("usage") or {}
    return _response(
        parts,
        FINISH_REASONS.get(choice.get("finish_reason"), "STOP"),
        usage.get("prompt_tokens") or 0,
        usage.get("completion_tokens") or 0,
    )


class OpenAICompatClient:
    def __init__(self, base_url: str, api_key: str, model: str):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.headers = {"Authorization": f"Bearer {api_key or 'none'}"}
        self.model = model

    async def generate(self, system_prompt: str, tools: list[dict] | None, contents: list):
        body = {
            "model": self.model,
            "messages": to_openai_messages(system_prompt, contents),
            "temperature": 0.2,
            "max_tokens": 8192,
        }
        if tools:
            body["tools"] = to_openai_tools(tools)
            body["tool_choice"] = "auto"
        async with httpx.AsyncClient(timeout=180) as client:
            r = await client.post(self.url, headers=self.headers, json=body)
        # Groq rejects a reply whose tool call does not parse; the loop recovers from that.
        if r.status_code == 400 and "tool_use_failed" in r.text:
            return _response([], "MALFORMED_FUNCTION_CALL")
        r.raise_for_status()
        return from_openai_response(r.json())
