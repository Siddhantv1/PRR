import asyncio
import inspect
import sys

from dotenv import load_dotenv

sys.path.insert(0, ".")
load_dotenv()

from backend.agents.base import AgentBase
from backend.mcp_server.server import ToolServer


async def main():
    # 1. Verify schema conversion
    ts = ToolServer("/tmp", "test", "test")
    schemas = ts.get_gemini_tools()
    assert all("parameters" in s for s in schemas), "FAIL: tool still has input_schema key"
    assert all("input_schema" not in s for s in schemas), "FAIL: input_schema not removed"
    assert all(
        "additionalProperties" not in str(s) for s in schemas
    ), "FAIL: additionalProperties present"
    print(f"✓ Tool schemas converted correctly ({len(schemas)} tools)")

    # 2. Verify single call (no tools) works
    events = []

    async def broadcast(e):
        events.append(e)

    class MinimalTS:
        def get_gemini_tools(self):
            return []

        async def call_tool(self, n, a):
            return {"content": [{"type": "text", "text": "ok"}]}

    agent = AgentBase(MinimalTS(), broadcast)
    text, tokens = await agent.run_single_call(
        "You are a test assistant. Reply with exactly: GEMINI_OK",
        "Say the magic word.",
    )
    assert "GEMINI_OK" in text, f"FAIL: expected GEMINI_OK in response, got: {text!r}"
    assert tokens > 0, "FAIL: token count is 0"
    print(f"✓ Single call works. Tokens: {tokens}. Response: {text[:60]}")

    # 3. Verify async (not sync) client used
    src = inspect.getsource(AgentBase)
    assert (
        "client.aio.models" in src
    ), "FAIL: async client call not found (should be client.aio.models)"
    assert (
        "client.models.generate_content" not in src
    ), "FAIL: sync client used (should be client.aio.models)"
    print("✓ Async client confirmed in run_loop")

    print("\n✅ All checks passed. Gemini port is correct.")


asyncio.run(main())
