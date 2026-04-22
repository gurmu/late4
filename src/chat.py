"""
Conversational Orchestrator (Semantic Kernel multi-agent, GCC)
"""

import asyncio
import os
import sys
from uuid import uuid4

from dotenv import load_dotenv

from agents.multi_agent_orchestrator import MultiAgentOrchestrator
from core.logging import setup_logging

load_dotenv()
logger = setup_logging(__name__)


def get_conversation_id() -> str:
    return os.getenv("CONVERSATION_ID", str(uuid4()))


async def main_async():
    os.system("cls" if os.name == "nt" else "clear")

    print("=" * 70)
    print("ITSM Knowledge-Based Assistant (GCC, Multi-Agent)")
    print("=" * 70)
    print("\nType 'quit' to exit\n")
    print("=" * 70)

    conversation_id = get_conversation_id()
    orchestrator = MultiAgentOrchestrator()

    while True:
        user_input = input("\nYou: ").strip()
        if user_input.lower() in ["quit", "exit", "bye"]:
            print("\nGoodbye!")
            break
        if not user_input:
            print("Please enter a message.")
            continue

        print("\nAssistant: ", end="", flush=True)
        response = await orchestrator.run_conversation(user_input, conversation_id)
        print(response)


def main():
    try:
        asyncio.run(main_async())
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
