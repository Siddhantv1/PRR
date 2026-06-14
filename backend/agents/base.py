import asyncio
from collections.abc import Awaitable, Callable

import google.genai as genai
import google.genai.types as gtypes
from google.genai import errors as genai_errors

try:
    from google.api_core import exceptions as gexc
except ImportError:
    gexc = None

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
        self.client = genai.Client(api_key=config.GOOGLE_API_KEY)

    def _build_config(
        self,
        system_prompt: str,
        tools: list[dict] | None = None,
    ) -> gtypes.GenerateContentConfig:
        """Build GenerateContentConfig with system instruction and optional tools."""
        config_kwargs = {
            "system_instruction": system_prompt,
            "max_output_tokens": 8192,
            "temperature": 0.2,
        }
        if tools:
            function_declarations = [
                gtypes.FunctionDeclaration.model_validate(tool) for tool in tools
            ]
            if function_declarations:
                # Gemini defaults to AUTO function calling when declarations exist.
                # Supplying an explicit tool_config can trigger INVALID_ARGUMENT if
                # the API decides the declarations are absent after normalization.
                config_kwargs["tools"] = [
                    gtypes.Tool(function_declarations=function_declarations)
                ]
        return gtypes.GenerateContentConfig(**config_kwargs)

    def _extract_parts(self, response) -> tuple[list[str], list]:
        """
        Extract text parts and function_call parts from a Gemini response.

        Returns (text_list, function_call_list). Gemini may return multiple
        parts in one response, so callers must handle all of them.
        """
        texts = []
        calls = []
        try:
            candidate = response.candidates[0]
            for part in candidate.content.parts:
                if hasattr(part, "text") and part.text:
                    texts.append(part.text)
                if hasattr(part, "function_call") and part.function_call:
                    calls.append(part.function_call)
        except (IndexError, AttributeError, TypeError):
            pass
        if not calls:
            calls = list(getattr(response, "function_calls", None) or [])
        return texts, calls

    def _count_tokens(self, response) -> int:
        """Extract token usage from Gemini response metadata."""
        try:
            metadata = response.usage_metadata
            return (metadata.prompt_token_count or 0) + (
                metadata.candidates_token_count or 0
            )
        except (AttributeError, TypeError):
            return 0

    def _is_finished(self, response) -> bool:
        """
        Return True when Gemini is done and is not requesting tool calls.

        Finish reasons include STOP, MAX_TOKENS, SAFETY, RECITATION, and OTHER.
        This loop continues only when the response contains function calls.
        """
        _, calls = self._extract_parts(response)
        return len(calls) == 0

    async def run_loop(
        self,
        system_prompt: str,
        initial_message: str,
        max_iterations: int | None = None,
        extra_tools: list[dict] | None = None,
        allowed_tools: set[str] | None = None,
        max_tool_calls: int | None = None,
    ) -> tuple[str, int]:
        """
        Run the tool-use loop. Returns (final_text, total_tokens).

        Gemini requires alternating user/model roles. Multiple tool results from
        one model response are batched into a single user turn.
        """
        tools = self._get_tool_declarations(allowed_tools)
        if extra_tools:
            tools.extend(extra_tools)

        system_with_budget = self._with_tool_budget_rules(system_prompt)
        tool_cfg = self._build_config(system_with_budget, tools)
        text_only_cfg = self._build_config(system_with_budget, tools=None)
        contents = [{"role": "user", "parts": [{"text": initial_message}]}]

        total_tokens = 0
        iterations = 0
        tool_calls_made = 0
        tool_budget_exhausted = False
        max_iter = max_iterations or config.MAX_AGENT_ITERATIONS

        while iterations < max_iter:
            iterations += 1

            cfg = text_only_cfg if tool_budget_exhausted else tool_cfg
            response = await self._generate_content_with_retries(cfg, contents)
            total_tokens += self._count_tokens(response)

            texts, calls = self._extract_parts(response)
            if not texts and not calls:
                if self._is_malformed_function_call(response) and not tool_budget_exhausted:
                    tool_budget_exhausted = True
                    await self.broadcast(
                        {
                            "type": "info",
                            "message": (
                                "Gemini returned a malformed function call. "
                                "Continuing without tools and asking for a final answer."
                            ),
                        }
                    )
                    continue
                raise RuntimeError(
                    "Gemini returned empty response "
                    f"({self._response_diagnostics(response)}) -- possible SAFETY block. "
                    "Try rephrasing the system prompt."
                )

            for text in texts:
                if text.strip():
                    await self.broadcast({"type": "agent_text", "text": text})

            if not calls:
                return "\n".join(texts), total_tokens

            model_content = self._response_content(response)
            if model_content is not None and getattr(model_content, "parts", None):
                contents.append(model_content)
            else:
                contents.append(
                    {
                        "role": "model",
                        "parts": [
                            {
                                "function_call": {
                                    "name": call.name,
                                    "args": dict(call.args) if call.args else {},
                                }
                            }
                            for call in calls
                        ],
                    }
                )

            function_response_parts = []
            for call in calls:
                tool_calls_made += 1
                args = dict(call.args) if call.args else {}
                await self.broadcast(
                    {
                        "type": "tool_call",
                        "tool": call.name,
                        "args": args,
                        "id": call.name,
                    }
                )

                result = await self.tool_server.call_tool(call.name, args)
                result_text = result["content"][0]["text"]
                is_error = result.get("isError", False)

                await self.broadcast(
                    {
                        "type": "tool_result",
                        "tool": call.name,
                        "summary": result_text[:200],
                        "ok": not is_error,
                    }
                )

                function_response_parts.append(
                    {
                        "function_response": {
                            "name": call.name,
                            "response": {
                                "result": result_text,
                                "error": is_error,
                            },
                        }
                    }
                )

            contents.append({"role": "user", "parts": function_response_parts})

            if max_tool_calls is not None and tool_calls_made >= max_tool_calls:
                tool_budget_exhausted = True
                await self.broadcast(
                    {
                        "type": "info",
                        "message": (
                            f"Tool budget reached ({tool_calls_made}/{max_tool_calls}). "
                            "Asking agent to summarize with gathered evidence."
                        ),
                    }
                )

        raise RuntimeError(f"Agent exceeded max iterations ({max_iter})")

    def _get_tool_declarations(self, allowed_tools: set[str] | None) -> list[dict]:
        try:
            return self.tool_server.get_gemini_tools(allowed_tools)
        except TypeError:
            tools = self.tool_server.get_gemini_tools()
            if allowed_tools is None:
                return tools
            return [tool for tool in tools if tool["name"] in allowed_tools]

    def _with_tool_budget_rules(self, system_prompt: str) -> str:
        return f"""{system_prompt}

TOOL BUDGET RULES:
- Do not repeat the same tool call with the same arguments.
- If a search or listing tool returns empty results, do not retry the same query.
- Prefer one targeted query over several broad queries.
- Once you have enough evidence to answer the stage, stop calling tools and produce the requested final output.
"""

    async def run_single_call(
        self,
        system_prompt: str,
        user_message: str,
    ) -> tuple[str, int]:
        """
        Single Gemini call with no tools. For review/analysis stages.

        This does not enter the tool loop.
        """
        cfg = self._build_config(system_prompt, tools=None)

        response = await self._generate_content_with_retries(
            cfg,
            [{"role": "user", "parts": [{"text": user_message}]}],
        )

        total_tokens = self._count_tokens(response)
        texts, _ = self._extract_parts(response)
        final_text = "\n".join(texts)

        await self.broadcast({"type": "agent_text", "text": final_text})
        return final_text, total_tokens

    async def _generate_content_with_retries(
        self,
        cfg: gtypes.GenerateContentConfig,
        contents: list[dict],
    ):
        for attempt in range(3):
            try:
                return await self.client.aio.models.generate_content(
                    model=config.MODEL,
                    config=cfg,
                    contents=contents,
                )
            except Exception as exc:
                if self._is_resource_exhausted(exc):
                    if attempt == 2:
                        raise
                    wait = 30 * (attempt + 1)
                    await self.broadcast(
                        {
                            "type": "info",
                            "message": f"Rate limit hit. Waiting {wait}s...",
                        }
                    )
                    await asyncio.sleep(wait)
                    continue
                if self._is_service_unavailable(exc):
                    if attempt == 2:
                        raise
                    await asyncio.sleep(10)
                    continue
                raise

        raise RuntimeError("Gemini request failed after retries")

    def _response_content(self, response):
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return None
        return getattr(candidates[0], "content", None)

    def _response_diagnostics(self, response) -> str:
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return "no candidates"
        candidate = candidates[0]
        finish_reason = getattr(candidate, "finish_reason", None)
        finish_message = getattr(candidate, "finish_message", None)
        safety_ratings = getattr(candidate, "safety_ratings", None)
        parts = getattr(getattr(candidate, "content", None), "parts", None)
        part_count = len(parts) if parts else 0
        return (
            f"finish_reason={finish_reason}, "
            f"finish_message={finish_message!r}, "
            f"part_count={part_count}, "
            f"safety_ratings={safety_ratings}"
        )

    def _is_malformed_function_call(self, response) -> bool:
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return False
        finish_reason = getattr(candidates[0], "finish_reason", None)
        return (
            finish_reason == "MALFORMED_FUNCTION_CALL"
            or getattr(finish_reason, "name", None) == "MALFORMED_FUNCTION_CALL"
        )

    def _is_resource_exhausted(self, exc: Exception) -> bool:
        if gexc is not None and isinstance(exc, gexc.ResourceExhausted):
            return True
        return isinstance(exc, genai_errors.APIError) and (
            exc.code == 429 or exc.status == "RESOURCE_EXHAUSTED"
        )

    def _is_service_unavailable(self, exc: Exception) -> bool:
        if gexc is not None and isinstance(exc, gexc.ServiceUnavailable):
            return True
        return isinstance(exc, genai_errors.APIError) and (
            exc.code == 503 or exc.status == "UNAVAILABLE"
        )
