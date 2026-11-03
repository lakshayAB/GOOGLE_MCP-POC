"""Terminal chat with the Google Ads agent."""

import asyncio
import json

from app.agent import Agent, ends_with_model_reply, user_message
from app.config import load_settings, missing_config, resolve_google_credentials
from app.mcp_client import GoogleAdsMCP


async def main() -> None:
    missing = missing_config()
    if missing:
        print(f"Missing in .env: {', '.join(missing)}")
        return
    resolve_google_credentials()
    settings = load_settings()

    print("Starting Google Ads MCP server...")
    mcp = GoogleAdsMCP(settings.mcp_command, settings.mcp_env)
    await mcp.start()
    agent = Agent(settings, mcp)
    print(f"Ready ({settings.model}). Type a question, 'reset' for a new chat, 'exit' to quit.\n")

    history = []
    try:
        while True:
            try:
                text = input("you> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not text:
                continue
            if text.lower() in ("exit", "quit"):
                break
            if text.lower() == "reset":
                history.clear()
                print("(new chat)\n")
                continue

            checkpoint = len(history)
            history.append(user_message(text))
            print("ai> ", end="", flush=True)
            try:
                async for ev in agent.run(history):
                    if ev["type"] == "text":
                        print(ev["text"], end="", flush=True)
                    elif ev["type"] == "tool_start":
                        print(f"\n  [tool] {ev['name']} {json.dumps(ev['input'])}", flush=True)
                    elif ev["type"] == "tool_end":
                        status = "ERROR" if ev["is_error"] else "ok"
                        print(f"  [{status}] {ev['preview'][:300]}\n", flush=True)
                    elif ev["type"] in ("notice", "error"):
                        print(f"\n  ({ev['message']})", flush=True)
            except Exception as exc:
                print(f"\n  (error: {type(exc).__name__}: {exc})")
            # Drop a turn that didn't finish so the history stays valid.
            if not ends_with_model_reply(history):
                del history[checkpoint:]
            print("\n")
    finally:
        await mcp.stop()


if __name__ == "__main__":
    asyncio.run(main())
