from collections.abc import Awaitable, Callable
from typing import Optional

import anthropic

from backend.config import config
from backend.mcp_server.server import ToolServer


class AgentBase:
    def __init__(
        self,
        tool_server: ToolServer,
        broadcast_fn: Callable[[dict], Awaitable[None]],
    ):
        self.tool_server = tool_server
        self.broadcast = broadcast_fn
        self.client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)

    async def run_loop(
        self,
        system_prompt: str,
        initial_message: str,
        max_iterations: Optional[int] = None,
        extra_tools: Optional[list[dict]] = None,
    ) -> tuple[str, int]:
        """
        Run the tool-use loop. Returns (final_text, total_tokens).
        max_iterations defaults to config.MAX_AGENT_ITERATIONS.
        extra_tools: additional tool schemas beyond the tool_server's (rarely needed).
        """
        tools = self.tool_server.get_tool_schemas()
        if extra_tools:
            tools.extend(extra_tools)

        messages = [{"role": "user", "content": initial_message}]
        total_tokens = 0
        iterations = 0
        max_iter = max_iterations or config.MAX_AGENT_ITERATIONS

        while iterations < max_iter:
            iterations += 1
            response = await self.client.messages.create(
                model=config.MODEL,
                max_tokens=8096,
                system=system_prompt,
                tools=tools,
                messages=messages,
            )
            total_tokens += response.usage.input_tokens + response.usage.output_tokens

            tool_use_blocks = []
            text_blocks = []
            for block in response.content:
                if block.type == "text":
                    text_blocks.append(block.text)
                elif block.type == "tool_use":
                    tool_use_blocks.append(block)

            for text in text_blocks:
                if text.strip():
                    await self.broadcast({"type": "agent_text", "text": text})

            if not tool_use_blocks:
                final_text = "\n".join(text_blocks)
                return final_text, total_tokens

            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in tool_use_blocks:
                await self.broadcast(
                    {
                        "type": "tool_call",
                        "tool": block.name,
                        "args": block.input,
                        "id": block.id,
                    }
                )
                result = await self.tool_server.call_tool(block.name, block.input)
                result_text = result["content"][0]["text"]
                is_error = result.get("isError", False)
                await self.broadcast(
                    {
                        "type": "tool_result",
                        "tool": block.name,
                        "summary": result_text[:200],
                        "ok": not is_error,
                    }
                )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_text,
                    }
                )

            messages.append({"role": "user", "content": tool_results})

        raise RuntimeError(f"Agent exceeded max iterations ({max_iter})")

    async def run_single_call(
        self,
        system_prompt: str,
        user_message: str,
    ) -> tuple[str, int]:
        """Single Claude call with no tool use. For review/analysis stages."""
        response = await self.client.messages.create(
            model=config.MODEL,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        text = response.content[0].text
        tokens = response.usage.input_tokens + response.usage.output_tokens
        await self.broadcast({"type": "agent_text", "text": text})
        return text, tokens
