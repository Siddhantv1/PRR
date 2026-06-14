import asyncio
import json
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
        cfg = gtypes.GenerateContentConfig(
            system_instruction=system_prompt,
            max_output_tokens=8192,
            temperature=0.2,
        )
        if tools:
            cfg.tools = [gtypes.Tool(function_declarations=tools)]
            mode_enum = getattr(gtypes.FunctionCallingConfig, "Mode", None)
            auto_mode = (
                mode_enum.AUTO
                if mode_enum is not None
                else gtypes.FunctionCallingConfigMode.AUTO
            )
            cfg.tool_config = gtypes.ToolConfig(
                function_calling_config=gtypes.FunctionCallingConfig(mode=auto_mode)
            )
        return cfg

    def _extract_parts(self, response) -> tuple[list[str], list, str]:
        """
        Extract text parts, function_call parts, and finish reason.

        Returns (text_list, function_call_list, finish_reason). Gemini may
        return multiple parts in one response, so callers must handle all of them.
        """
        texts, calls = [], []
        finish_reason = "STOP"
        try:
            candidate = response.candidates[0]
            raw_finish_reason = getattr(candidate, "finish_reason", "STOP")
            finish_reason = getattr(
                raw_finish_reason, "name", str(raw_finish_reason)
            ).upper()
            if not hasattr(candidate, "content") or not candidate.content:
                return texts, calls, finish_reason
            for part in candidate.content.parts:
                if hasattr(part, "text") and part.text and part.text.strip():
                    texts.append(part.text)
                if hasattr(part, "function_call") and part.function_call:
                    if (
                        hasattr(part.function_call, "name")
                        and part.function_call.name
                    ):
                        calls.append(part.function_call)
        except (IndexError, AttributeError, TypeError):
            pass
        if not calls:
            calls = list(getattr(response, "function_calls", None) or [])
        return texts, calls, finish_reason

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
        _, calls, _ = self._extract_parts(response)
        return len(calls) == 0

    async def run_loop(
        self,
        system_prompt: str,
        initial_message: str,
        max_iterations: int | None = None,
        extra_tools: list[dict] | None = None,
        allowed_tools: list[str] | set[str] | None = None,
        max_tool_calls: int | None = None,
        pressure_at: int | None = None,
        pressure_message: str | None = None,
        initial_contents: list | None = None,
        return_history: bool = False,
    ) -> tuple[str, int] | tuple[str, int, list]:
        """
        Run the tool-use loop.

        Returns (final_text, total_tokens), or (final_text, total_tokens,
        contents) when return_history=True.

        Gemini requires alternating user/model roles. Multiple tool results from
        one model response are batched into a single user turn.
        """
        tools = self.tool_server.get_gemini_tools()
        if extra_tools:
            tools.extend(extra_tools)
        if allowed_tools is not None:
            allowed_tool_names = set(allowed_tools)
            tools = [tool for tool in tools if tool["name"] in allowed_tool_names]

        system_with_budget = self._with_tool_budget_rules(system_prompt)
        tool_cfg = self._build_config(system_with_budget, tools)
        text_only_cfg = self._build_config(system_with_budget, tools=None)
        if initial_contents:
            contents = list(initial_contents)
            contents.append({"role": "user", "parts": [{"text": initial_message}]})
        else:
            contents = [{"role": "user", "parts": [{"text": initial_message}]}]

        total_tokens = 0
        iterations = 0
        tool_calls_made = 0
        tool_budget_exhausted = False
        max_iter = max_iterations or config.MAX_AGENT_ITERATIONS
        last_texts: list[str] = []
        seen_calls: dict[str, str] = {}
        pressure_injected = False

        while iterations < max_iter:
            iterations += 1
            if (
                pressure_at
                and not pressure_injected
                and iterations >= pressure_at
                and pressure_message
            ):
                contents.append({"role": "user", "parts": [{"text": pressure_message}]})
                pressure_injected = True
                await self.broadcast(
                    {
                        "type": "info",
                        "message": f"[Pressure injected at iter {iterations}]",
                    }
                )

            cfg = text_only_cfg if tool_budget_exhausted else tool_cfg
            response = await self._generate_content_with_retries(cfg, contents)
            total_tokens += self._count_tokens(response)

            texts, calls, finish_reason = self._extract_parts(response)
            last_texts = texts

            if not texts and not calls:
                if "MALFORMED" in finish_reason:
                    tool_budget_exhausted = True
                    await self.broadcast(
                        {
                            "type": "info",
                            "message": (
                                f"MALFORMED_FUNCTION_CALL at iter {iterations}. "
                                "Recovering..."
                            ),
                        }
                    )
                    recovery_msg = (
                        "Your last tool call was malformed. Do NOT call any tools "
                        "right now. Respond in plain text only: summarize what you "
                        "know so far and what your next action will be."
                    )
                    contents.append({"role": "user", "parts": [{"text": recovery_msg}]})
                    continue

                await self.broadcast(
                    {
                        "type": "info",
                        "message": (
                            f"Empty response at iter {iterations} "
                            f"(finish={finish_reason}). Retrying with clarification."
                        ),
                    }
                )
                if finish_reason == "SAFETY":
                    contents.append(
                        {
                            "role": "user",
                            "parts": [
                                {
                                    "text": (
                                        "Please continue. Focus only on the code "
                                        "change needed. Respond plainly."
                                    )
                                }
                            ],
                        }
                    )
                else:
                    contents.append(
                        {
                            "role": "user",
                            "parts": [{"text": "Please continue with your analysis."}],
                        }
                    )
                continue

            if "MALFORMED" in finish_reason:
                tool_budget_exhausted = True
                await self.broadcast(
                    {
                        "type": "info",
                        "message": (
                            f"MALFORMED_FUNCTION_CALL at iter {iterations}. "
                            "Recovering..."
                        ),
                    }
                )
                model_parts = [{"text": text} for text in texts if text.strip()]
                if model_parts:
                    contents.append({"role": "model", "parts": model_parts})
                recovery_msg = (
                    "Your last tool call was malformed. Do NOT call any tools right "
                    "now. Respond in plain text only: summarize what you know so far "
                    "and what your next action will be."
                )
                contents.append({"role": "user", "parts": [{"text": recovery_msg}]})
                continue

            for text in texts:
                if text.strip():
                    await self.broadcast({"type": "agent_text", "text": text})
                    if "CONTRIBUTOR_DONE" in text:
                        result_text = "\n".join(last_texts)
                        return (
                            (result_text, total_tokens, contents)
                            if return_history
                            else (result_text, total_tokens)
                        )

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

            if not calls:
                final_text = "\n".join(texts)
                return (
                    (final_text, total_tokens, contents)
                    if return_history
                    else (final_text, total_tokens)
                )

            function_response_parts = []
            for call in calls:
                tool_calls_made += 1
                args = dict(call.args) if call.args else {}
                serialized_args = json.dumps(args, sort_keys=True, default=str)
                dedup_key = f"{call.name}:{serialized_args}"

                if dedup_key in seen_calls:
                    cached = seen_calls[dedup_key]
                    await self.broadcast(
                        {
                            "type": "tool_result",
                            "tool": call.name,
                            "summary": f"[CACHED] {cached[:100]}",
                            "ok": True,
                        }
                    )
                    function_response_parts.append(
                        {
                            "function_response": {
                                "name": call.name,
                                "response": {
                                    "result": f"[Already retrieved] {cached}",
                                    "cached": True,
                                },
                            }
                        }
                    )
                    continue

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
                if not is_error:
                    seen_calls[dedup_key] = result_text

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

        final_text = "\n".join(last_texts)
        await self.broadcast(
            {"type": "info", "message": f"Max iterations ({max_iter}) reached."}
        )
        return (
            (final_text, total_tokens, contents)
            if return_history
            else (final_text, total_tokens)
        )

    def _get_tool_declarations(
        self, allowed_tools: list[str] | set[str] | None
    ) -> list[dict]:
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
        texts, _, _ = self._extract_parts(response)
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
                    await asyncio.sleep(10 * (attempt + 1))
                    continue
                if attempt == 2:
                    raise
                await asyncio.sleep(5)

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
        normalized = getattr(finish_reason, "name", str(finish_reason)).upper()
        return "MALFORMED" in normalized

    def _is_resource_exhausted(self, exc: Exception) -> bool:
        if gexc is not None and isinstance(exc, gexc.ResourceExhausted):
            return True
        if isinstance(exc, genai_errors.APIError) and (
            exc.code == 429 or exc.status == "RESOURCE_EXHAUSTED"
        ):
            return True
        err_str = str(exc)
        return (
            "429" in err_str
            or "ResourceExhausted" in err_str
            or "RATE" in err_str.upper()
        )

    def _is_service_unavailable(self, exc: Exception) -> bool:
        if gexc is not None and isinstance(exc, gexc.ServiceUnavailable):
            return True
        if isinstance(exc, genai_errors.APIError) and (
            exc.code == 503 or exc.status == "UNAVAILABLE"
        ):
            return True
        err_str = str(exc)
        return "503" in err_str or "ServiceUnavailable" in err_str
