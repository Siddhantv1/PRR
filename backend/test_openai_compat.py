"""Offline check of the OpenAI-compatible adapter: python backend/test_openai_compat.py"""

import asyncio
import json
import os
import sys
from pathlib import Path

os.environ["LLM_PROVIDER"] = "openai"
os.environ.setdefault("GITHUB_TOKEN", "test")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.agents.base import AgentBase
from backend.agents.openai_compat import from_openai_response, to_openai_messages


def completion(content=None, calls=(), finish="stop"):
    return {
        "choices": [
            {
                "finish_reason": finish,
                "message": {
                    "content": content,
                    "tool_calls": [
                        {"id": f"x{i}", "type": "function",
                         "function": {"name": name, "arguments": json.dumps(args)}}
                        for i, (name, args) in enumerate(calls)
                    ],
                },
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }


class FakeTools:
    def get_gemini_tools(self, allowed_names=None):
        return [{"name": "read_file", "description": "Read a file.",
                 "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}]

    async def call_tool(self, name, args):
        return {"content": [{"text": f"contents of {args['path']}"}]}


def check_conversion():
    history = [
        {"role": "user", "parts": [{"text": "fix it"}]},
        {"role": "model", "parts": [
            {"text": "reading"},
            {"function_call": {"name": "read_file", "args": {"path": "a.go"}}},
            {"function_call": {"name": "read_file", "args": {"path": "b.go"}}},
        ]},
        {"role": "user", "parts": [
            {"function_response": {"name": "read_file", "response": {"result": "A"}}},
            {"function_response": {"name": "read_file", "response": {"result": "B"}}},
        ]},
        {"role": "user", "parts": [{"text": "wrap up"}]},
    ]
    msgs = to_openai_messages("sys", history)
    roles = [m["role"] for m in msgs]
    assert roles == ["system", "user", "assistant", "tool", "tool", "user"], roles
    ids = [c["id"] for c in msgs[2]["tool_calls"]]
    assert [m["tool_call_id"] for m in msgs[3:5]] == ids, "tool results must pair with calls by position"
    assert json.loads(msgs[3]["content"]) == {"result": "A"}


def check_parsing():
    r = from_openai_response(completion("hi", [("read_file", {"path": "x"})], "tool_calls"))
    parts = r.candidates[0].content.parts
    assert parts[0].text == "hi" and parts[1].function_call.args == {"path": "x"}
    assert r.usage_metadata.prompt_token_count == 10

    bad = completion(calls=[("read_file", {})])
    bad["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = "{not json"
    assert from_openai_response(bad).candidates[0].finish_reason == "MALFORMED_FUNCTION_CALL"


async def check_loop():
    events = []

    async def broadcast(event):
        events.append(event)

    agent = AgentBase(FakeTools(), broadcast)
    replies = [
        completion("looking", [("read_file", {"path": "main.go"})], "tool_calls"),
        completion("CONTRIBUTOR_DONE"),
    ]
    sent = []

    async def fake_generate(system, tools, contents):
        sent.append(to_openai_messages(system, contents))
        return from_openai_response(replies.pop(0))

    agent.client.generate = fake_generate
    text, tokens, history = await agent.run_loop("sys", "go", return_history=True)

    assert "CONTRIBUTOR_DONE" in text and tokens == 30, (text, tokens)
    second = sent[1]
    assert second[-1]["role"] == "tool" and "contents of main.go" in second[-1]["content"]
    assert second[-1]["tool_call_id"] == second[-2]["tool_calls"][0]["id"]
    assert any(e["type"] == "tool_result" and e["ok"] for e in events)


if __name__ == "__main__":
    check_conversion()
    check_parsing()
    asyncio.run(check_loop())
    print("openai_compat: all checks passed")
