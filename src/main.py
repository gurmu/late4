"""
Main Orchestrator (Semantic Kernel multi-agent, GCC)
"""

import asyncio
import json
import sys
from dataclasses import asdict

from dotenv import load_dotenv

from agents.multi_agent_orchestrator import MultiAgentOrchestrator, TicketRequest
from core.logging import setup_logging

load_dotenv()
logger = setup_logging(__name__)


def build_ticket(args) -> TicketRequest:
    return TicketRequest(
        subject=args.subject,
        description=args.description,
        user_email=args.email,
        phone_number=args.phone,
        user_first_name=args.first_name,
        user_last_name=args.last_name,
        additional_context=args.context,
    )


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="ITSM Knowledge-Based Ticket Triage (GCC, Multi-Agent)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--subject", required=True, help="Ticket subject/title")
    parser.add_argument("--description", required=True, help="Detailed ticket description")
    parser.add_argument("--email", required=True, help="Customer email address")
    parser.add_argument("--phone", required=True, help="Customer phone number")
    parser.add_argument("--first-name", help="Customer first name")
    parser.add_argument("--last-name", help="Customer last name")
    parser.add_argument("--context", help="Additional context or notes")
    parser.add_argument("--conversation-id", required=True, help="Conversation thread ID")

    args = parser.parse_args()

    try:
        orchestrator = MultiAgentOrchestrator()
        ticket = build_ticket(args)
        result = asyncio.run(orchestrator.run_ticket_triage(ticket, args.conversation_id))

        # ---- Human-readable output (what Teams users see) ----
        print("\n" + "=" * 70)
        print("💬  TEAMS BOT RESPONSE (what the user sees)")
        print("=" * 70)
        print(result.user_message or result.orchestrator_summary or "(no response)")
        print("=" * 70)

        # ---- Full debug triage payload ----
        print("\n" + "-" * 70)
        print("🔍  FULL TRIAGE RESULT (debug)")
        print("-" * 70)
        print(json.dumps(asdict(result), indent=2))
        print("-" * 70 + "\n")

        sys.exit(0)

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
