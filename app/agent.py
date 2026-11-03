"""Streaming agent loop: Gemini <-> Google Ads MCP tools."""

from collections.abc import AsyncIterator
from typing import Any

from google import genai
from google.genai import types

from .config import Settings
from .mcp_client import GoogleAdsMCP
from .prompts import SYSTEM_PROMPT

MAX_TOOL_ROUNDS = 15
MAX_MALFORMED_RETRIES = 2
BLOCKED = {"SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "RECITATION"}


class Agent:
    def __init__(self, settings: Settings, mcp: GoogleAdsMCP):
        self.settings = settings
        self.mcp = mcp
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=[types.Tool(function_declarations=[
                types.FunctionDeclaration(
                    name=t["name"],
                    description=t["description"],
                    parameters_json_schema=t["input_schema"],
                )
                for t in mcp.tools
            ])],
            # We run the tools ourselves so the UI can show each call.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

    async def run(self, history: list[types.Content]) -> AsyncIterator[dict[str, Any]]:
        """Advance the conversation in `history` (mutated in place, append-only).

        Yields UI events: text, tool_start, tool_end, notice, error.
        """
        malformed = 0
        for _ in range(MAX_TOOL_ROUNDS):
            parts: list[types.Part] = []
            finish = None
            stream = await self.client.aio.models.generate_content_stream(
                model=self.settings.model, contents=history, config=self.config,
            )
            async for chunk in stream:
                if not chunk.candidates:
                    continue
                cand = chunk.candidates[0]
                if cand.finish_reason:
                    finish = cand.finish_reason.name
                for part in (cand.content.parts if cand.content and cand.content.parts else []):
                    # Keep every part (thought signatures included) for the history.
                    parts.append(part)
                    if part.text and not part.thought:
                        yield {"type": "text", "text": part.text}

            if finish == "MALFORMED_FUNCTION_CALL":
                malformed += 1
                if malformed > MAX_MALFORMED_RETRIES:
                    yield {"type": "error", "message": "The model produced an invalid tool call. Please retry."}
                    return
                continue
            if finish in BLOCKED:
                yield {"type": "notice", "message": f"The model declined this request ({finish})."}
                if parts:
                    history.append(types.Content(role="model", parts=parts))
                return
            if not parts:
                yield {"type": "error", "message": "The model returned an empty response."}
                return

            history.append(types.Content(role="model", parts=parts))
            calls = [p.function_call for p in parts if p.function_call]
            if not calls:
                if finish == "MAX_TOKENS":
                    yield {"type": "notice", "message": "Response was cut off at the token limit."}
                return

            responses = []
            for i, call in enumerate(calls):
                call_id = call.id or f"{call.name}-{len(history)}-{i}"
                args = dict(call.args or {})
                yield {"type": "tool_start", "id": call_id, "name": call.name, "input": args}
                text, is_error = await self.mcp.call(call.name, args)
                yield {"type": "tool_end", "id": call_id, "name": call.name,
                       "is_error": is_error, "preview": text[:1500]}
                payload = {"error": text} if is_error else {"output": text}
                responses.append(types.Part(function_response=types.FunctionResponse(
                    id=call.id, name=call.name, response=payload,
                )))
            history.append(types.Content(role="user", parts=responses))

        yield {"type": "notice", "message": f"Stopped after {MAX_TOOL_ROUNDS} tool rounds."}


def user_message(text: str) -> types.Content:
    return types.Content(role="user", parts=[types.Part(text=text)])


def ends_with_model_reply(history: list[types.Content]) -> bool:
    return bool(history) and history[-1].role == "model" and not any(
        p.function_call for p in history[-1].parts or []
    )
