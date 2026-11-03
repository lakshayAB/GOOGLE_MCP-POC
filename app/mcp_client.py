"""Long-lived stdio connection to the official Google Ads MCP server."""

from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Tool results larger than this are truncated before being sent to the model.
MAX_RESULT_CHARS = 120_000


class GoogleAdsMCP:
    def __init__(self, command: list[str], env: dict[str, str]):
        self._params = StdioServerParameters(command=command[0], args=command[1:], env=env)
        self._stack = AsyncExitStack()
        self.session: ClientSession | None = None
        self.tools: list[dict[str, Any]] = []

    async def start(self) -> None:
        read, write = await self._stack.enter_async_context(stdio_client(self._params))
        self.session = await self._stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()
        listed = await self.session.list_tools()
        self.tools = [
            {"name": t.name, "description": t.description or "", "input_schema": t.input_schema}
            for t in sorted(listed.tools, key=lambda t: t.name)
        ]

    async def stop(self) -> None:
        await self._stack.aclose()

    async def call(self, name: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        """Run a tool; returns (text result, is_error)."""
        if self.session is None:
            return "Google Ads MCP server is not connected.", True
        try:
            result = await self.session.call_tool(name, arguments)
        except Exception as exc:  # transport or protocol failure
            return f"Tool call failed: {exc}", True

        parts = []
        for item in result.content:
            if getattr(item, "type", None) == "text":
                parts.append(item.text)
            else:
                parts.append(item.model_dump_json())
        if result.structured_content is not None and not parts:
            parts.append(str(result.structured_content))
        text = "\n".join(parts) or "(empty result)"
        if len(text) > MAX_RESULT_CHARS:
            text = text[:MAX_RESULT_CHARS] + "\n...[truncated - narrow the query with LIMIT or filters]"
        return text, bool(result.is_error)
