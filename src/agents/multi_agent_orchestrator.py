"""
Semantic Kernel multi-agent orchestration (GCC).

HYBRID APPROACH — "LLM decides, code enforces invariants":

1. KB-FIRST always: run ITSM search before any reasoning.
2. Python code enforces 4 NON-NEGOTIABLE invariants:
   - Invariant #1: kb_hits_count == 0 → KB_MISS is fact (LLM cannot claim KB_HIT)
   - Invariant #2: If LLM says urgency=="ambiguous" or proposed_action=="ask_user"
                    → block all tool calls, force the "Reply with 1 or 2" prompt
   - Invariant #3: Follow-up "1"/"2" only when conversation state is WAITING_FOR_CHOICE
   - Invariant #4: Before calling Ivanti/NICE, email (and phone for NICE) MUST be in
                    the conversation. If missing, ask the user and set WAITING_FOR_CONTACT.
3. LLM does all interpretation + routing (KB sufficiency, urgency, next action).
4. No KB_SCORE_THRESHOLD or top_score gating.  Scores logged but never routed on.
5. Tool call failures are captured, never crash the orchestration.
6. Persistent conversation state in Cosmos DB (survives across Teams activities).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from semantic_kernel import Kernel
from semantic_kernel.agents.chat_completion.chat_completion_agent import ChatCompletionAgent
from semantic_kernel.agents.group_chat.agent_group_chat import AgentGroupChat
from semantic_kernel.agents.strategies import TerminationStrategy
from semantic_kernel.connectors.ai.open_ai.services.azure_chat_completion import (
    AzureChatCompletion,
)

from agents.config.agent_config import AgentConfig
from agents.plugins.itsm_search_plugin import ITSMSearchPlugin
from agents.plugins.ivanti_plugin import IvantiPlugin
from agents.plugins.nice_plugin import NICEPlugin
from agents.chat_history.cosmos_chat_history import CosmosDBChatHistory

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Conversation state enum — persisted per conversation_id
# ---------------------------------------------------------------------------
class ConversationState(str, Enum):
    NEW = "new"                                    # fresh conversation
    WAITING_FOR_CHOICE = "waiting_for_choice"      # asked user "1 or 2", waiting
    WAITING_FOR_CONTACT = "waiting_for_contact"    # asked user for email/phone, waiting
    RESOLVED = "resolved"                          # final answer delivered


# In-memory state store keyed by conversation_id.
# In production Cosmos DB backs this; this dict is the process-level cache
# so state survives within a single bot process lifetime.  On restart
# the _is_followup_choice() heuristic still works via Cosmos history.
_conversation_states: dict[str, ConversationState] = {}


# ---------------------------------------------------------------------------
# Verbatim ask-user prompt (Invariant #2)
# ---------------------------------------------------------------------------
ASK_USER_PROMPT = (
    "I wasn't able to find a direct answer for this one in our knowledge base — "
    "but no worries, I can still get you help! 😊\n\n"
    "What would work best for you?\n\n"
    "**1)** Create an incident — this logs your issue, assigns it to the right team, "
    "and you'll get updates as it's worked on.\n\n"
    "**2)** Request a callback — a support specialist will call you back directly.\n\n"
    "Just reply **1** or **2** and I'll take care of it!"
)

# ---------------------------------------------------------------------------
# Verbatim contact-collection prompt (Invariant #4)
# ---------------------------------------------------------------------------
ASK_CONTACT_INCIDENT_PROMPT = (
    "Almost there! To create the incident I'll just need your contact details.\n\n"
    "Please reply with your **corporate email address** and I'll get that logged right away. "
    "(e.g. `jane.doe@peraton.com`)"
)

ASK_CONTACT_CALLBACK_PROMPT = (
    "Almost there! To schedule the callback I'll need your contact details.\n\n"
    "Please reply with your **corporate email address** and **phone number** "
    "so the specialist knows how to reach you. "
    "(e.g. `jane.doe@peraton.com, 240-555-0199`)"
)


@dataclass
class TicketRequest:
    subject: str
    description: str
    user_email: str
    phone_number: str
    user_first_name: str | None = None
    user_last_name: str | None = None
    additional_context: str | None = None


@dataclass
class TriageResult:
    """Consolidated output contract (Section F of spec)."""
    priority: str
    category: str
    team: str
    status: str = "success"
    orchestrator_summary: str = ""

    # KB tracking
    kb_used: bool = False
    kb_hits_count: int = 0
    kb_sufficient: bool = False
    kb_results: list[dict] = None

    # Actions & tool results
    actions: list[str] = None
    tool_results: dict = None       # {"ivanti": {...}, "nice": {...}}

    # Standard
    timestamp: str | None = None
    final: bool = True
    user_message: str = ""          # what Teams displays

    def __post_init__(self) -> None:
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat()
        if self.actions is None:
            self.actions = []
        if self.tool_results is None:
            self.tool_results = {}
        if self.kb_results is None:
            self.kb_results = []


# ======================================================================
# Termination strategy — ends agentic loop when Orchestrator emits
# "final": true  or  FINAL_RESOLUTION
# ======================================================================
class FinalResolutionTerminationStrategy(TerminationStrategy):
    async def should_agent_terminate(self, agent: ChatCompletionAgent, history) -> bool:
        if agent.name != "Orchestrator":
            return False
        if not history:
            return False
        last = history[-1].content or ""
        return (
            '"final": true' in last
            or '"final":true' in last
            or "FINAL_RESOLUTION" in last
        )


# ======================================================================
# Main Orchestrator
# ======================================================================
class MultiAgentOrchestrator:
    """
    Hybrid orchestrator: LLM decides, Python code enforces invariants.

    Flow:
    1. Pre-search KB (get structured JSON from ITSM plugin).
    2. If kb_hits_count == 0  →  Invariant #1: inject KB_MISS fact.
       If kb_hits_count > 0   →  inject results, let LLM judge sufficiency.
    3. AgentGroupChat runs (Orchestrator + ITSM + Ivanti + NICE agents).
    4. After LLM responds, Python enforces invariants on the output.
    5. Persist state + history to Cosmos.
    """

    def __init__(self, config: AgentConfig | None = None):
        self.config = config or AgentConfig()
        self.config.validate()

        self._history_store = CosmosDBChatHistory(
            endpoint=self.config.cosmos_endpoint,
            key=self.config.cosmos_key,
            database_name=self.config.cosmos_database,
            container_name=self.config.cosmos_container,
        )

        # Direct ITSM search instance for pre-search (before agentic flow)
        self._itsm_search = ITSMSearchPlugin(
            endpoint=self.config.azure_search_endpoint,
            index_name=self.config.azure_search_index,
            api_key=self.config.azure_search_key,
            content_field=self.config.kb_content_field,
            vision_endpoint=self.config.azure_vision_endpoint,
            vision_key=self.config.azure_vision_key,
        )

        # Build all 4 agents
        self._orchestrator_agent = self._build_orchestrator_agent()
        self._itsm_agent = self._build_itsm_agent()
        self._ivanti_agent = self._build_ivanti_agent()
        self._nice_agent = self._build_nice_agent()

    # ------------------------------------------------------------------
    # Kernel helper
    # ------------------------------------------------------------------
    def _build_kernel(self) -> Kernel:
        kernel = Kernel()
        service = AzureChatCompletion(
            service_id="chat",
            deployment_name=self.config.azure_openai_deployment,
            endpoint=self.config.azure_openai_endpoint,
            api_key=self.config.azure_openai_api_key,
            api_version=self.config.azure_openai_api_version,
        )
        kernel.add_service(service)
        return kernel

    # ------------------------------------------------------------------
    # Pre-search KB (structured JSON, no score gating)
    # ------------------------------------------------------------------
    def _pre_search_kb(self, query: str, image_bytes: bytes | None = None) -> dict:
        """
        Run ITSM search BEFORE agentic flow.

        If image_bytes is provided (user attached an image in Teams),
        it is injected into the search plugin for Azure Vision vectorizeImage.

        Returns parsed dict: {"kb_hits_count": int, "results": [...]}
        """
        # Inject image bytes for vision embedding (consumed during search)
        if image_bytes:
            self._itsm_search._pending_image_bytes = image_bytes
            logger.info(f"Image bytes injected for vision search: {len(image_bytes)} bytes")

        try:
            raw_json = self._itsm_search.search_kb(
                query=query,
                top_k=self.config.kb_top_k,
                semantic_config=self.config.kb_semantic_config or None,
                use_text_vectors=True,
                use_image_vectors=True,
            )
            parsed = json.loads(raw_json)
        except Exception as e:
            logger.error(f"KB pre-search failed: {e}")
            parsed = {"kb_hits_count": 0, "results": [], "error": str(e)}

        logger.info(f"KB pre-search: kb_hits_count={parsed.get('kb_hits_count', 0)}")
        return parsed

    # ------------------------------------------------------------------
    # Build context block to inject into user message
    # ------------------------------------------------------------------
    def _build_kb_context(self, kb_data: dict) -> str:
        """
        Build the context block that gets appended to the user message.

        - If kb_hits_count == 0:  insert KB_MISS invariant fact.
        - If kb_hits_count > 0:   insert results for LLM to judge.

        Results include both text articles and image screenshots from
        the ITSM knowledge base. Image results have an image_url field
        that the LLM should include in its response.
        """
        hits = kb_data.get("kb_hits_count", 0)

        lines: list[str] = ["", "--- KB SEARCH RESULTS ---"]

        if hits == 0:
            # Invariant #1: deterministic KB_MISS
            lines.append("KB_STATUS: KB_MISS  (kb_hits_count=0, this is a FACT)")
            lines.append("No knowledge base articles were returned for this query.")
            lines.append(
                "You MUST NOT claim that you found KB results. "
                "Proceed to the escalation decision flow."
            )
        else:
            # Count text vs image results for the LLM's awareness
            text_results = []
            image_results = []
            for r in kb_data.get("results", []):
                if r.get("image_url"):
                    image_results.append(r)
                else:
                    text_results.append(r)

            lines.append(f"KB_STATUS: KB_RESULTS_AVAILABLE  (kb_hits_count={hits})")
            lines.append(
                f"  Text articles: {len(text_results)}, Image/screenshot results: {len(image_results)}"
            )
            lines.append(
                "The following KB articles were returned. YOU decide whether they "
                "are sufficient to answer the user's question. Do NOT rely on "
                "scores for this decision — read the content and judge relevance."
            )
            lines.append(
                "IMPORTANT: If results include image_url fields, these are screenshots "
                "from ITSM procedure documents (step-by-step guides with visual aids). "
                "You MUST include relevant image URLs in your summary so the user can "
                "see the visual instructions. Format them as markdown images: "
                "![Step description](image_url)"
            )

            for i, r in enumerate(kb_data.get("results", []), 1):
                result_type = "IMAGE" if r.get("image_url") else "TEXT"
                lines.append(f"\n[Result {i}] ({result_type})")
                lines.append(f"  Source: {r.get('source', 'N/A')}")
                lines.append(f"  Content: {r.get('content', '')[:3000]}")
                if r.get("image_url"):
                    lines.append(f"  Image URL: {r['image_url']}")
                    lines.append("  ^ INCLUDE this image URL in your answer as a visual aid")
                if r.get("pdf_url"):
                    lines.append(f"  PDF URL: {r['pdf_url']}")

        lines.append("--- END KB SEARCH RESULTS ---")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Agent builders
    # ------------------------------------------------------------------
    def _build_orchestrator_agent(self) -> ChatCompletionAgent:
        kernel = self._build_kernel()

        instructions = (
            "You are the Orchestrator for an ITSM multi-agent system.\n"
            "You coordinate other agents and make ALL routing decisions using reasoning.\n\n"

            "## TONE & STYLE (for the 'summary' field)\n"
            "The 'summary' field is displayed directly to real employees in Microsoft Teams.\n"
            "Write it as a friendly, helpful IT support colleague — NOT a technical manual.\n"
            "Rules for 'summary':\n"
            "- Start with a brief empathetic acknowledgment (e.g., 'Hi! I found some steps that should help with your VPN issue.').\n"
            "- Use short, clear sentences. Avoid jargon where possible.\n"
            "- When listing steps, use numbered markdown but keep each step concise (one action per step).\n"
            "- IMPORTANT: Include ALL steps from the KB articles. Do NOT truncate or summarize a multi-step guide into just 2-3 steps. "
            "If the KB article has 8 steps, your summary must include all 8 steps.\n"
            "- End with an encouraging closing (e.g., 'Let me know if this doesn't resolve it and I'll escalate for you!').\n"
            "- Do NOT include raw source references like '[Result 1, Result 3]'. Instead, say something natural like 'Based on our IT knowledge base' if needed.\n"
            "- There is NO word limit for KB answers — be thorough. Include every step, detail, and visual aid from the KB results.\n"
            "- Use a warm, professional tone — imagine you're a helpful colleague in a Teams chat.\n\n"

            "## VISUAL AIDS & SCREENSHOTS\n"
            "KB search results may include IMAGE results with image_url fields.\n"
            "These are screenshots from ITSM procedure documents showing visual step-by-step instructions.\n"
            "Rules for handling images:\n"
            "- When KB results contain image_url fields, you MUST include them in your summary.\n"
            "- Format images as markdown: ![Brief description of what the screenshot shows](image_url)\n"
            "- Place each image near the relevant step it illustrates.\n"
            "- Example: After describing 'Step 3: Click Settings', include the screenshot showing the Settings menu.\n"
            "- If multiple images are available, include ALL relevant ones — they help the user follow visual instructions.\n"
            "- Images from the same source document (same file_name) are parts of the same procedure guide.\n\n"

            "## MANDATORY KB-FIRST WORKFLOW\n"
            "Every user message includes a '--- KB SEARCH RESULTS ---' block.\n"
            "Read it carefully and follow the rules below.\n\n"

            "### CASE A: KB_STATUS = KB_MISS  (kb_hits_count=0)\n"
            "This is a FACT set by the system. You MUST NOT claim you found KB results.\n"
            "Proceed directly to the ESCALATION DECISION FLOW (see below).\n\n"

            "### CASE B: KB_STATUS = KB_RESULTS_AVAILABLE  (kb_hits_count > 0)\n"
            "Read the returned KB articles and decide if they are SUFFICIENT to\n"
            "fully answer the user's question.\n\n"
            "Output your evaluation as JSON (only):\n"
            "{\n"
            '  "kb_sufficient": true | false,\n'
            '  "answer": "<user-facing answer if sufficient, else empty string>",\n'
            '  "classification": {"priority": "P1|P2|P3|P4", "category": "...", "team": "..."},\n'
            '  "reason": "<brief explanation of your sufficiency judgment>"\n'
            "}\n\n"
            "- If kb_sufficient=true:\n"
            "  → Your answer MUST incorporate ALL KB content — include every step, not just a summary.\n"
            "  → If KB results include images (image_url), INCLUDE them as markdown images in your answer.\n"
            "  → Combine information from MULTIPLE results if they come from the same source document.\n"
            "  → DO NOT call Ivanti or NICE agents.  KB answer is enough.\n"
            "  → Wrap your final output in the OUTPUT FORMAT below with kb_used=true, final=true.\n\n"
            "- If kb_sufficient=false:\n"
            "  → Proceed to the ESCALATION DECISION FLOW.\n\n"

            "## ESCALATION DECISION FLOW  (KB miss or insufficient)\n"
            "Analyze the user's message for urgency and intent, then output:\n"
            "{\n"
            '  "urgency": "urgent" | "non_urgent" | "ambiguous",\n'
            '  "proposed_action": "callback" | "incident" | "ask_user",\n'
            '  "reason": "<brief>"\n'
            "}\n\n"

            "### INVARIANT #2 — No side effects when ambiguous\n"
            "If urgency==\"ambiguous\" OR proposed_action==\"ask_user\":\n"
            "  → DO NOT call Ivanti or NICE agents.\n"
            "  → Return this EXACT message in your summary (verbatim):\n"
            f'  "{ASK_USER_PROMPT}"\n'
            "  → Set final=false.\n\n"

            "If urgency==\"urgent\" AND proposed_action==\"callback\":\n"
            "  → Ask the NICE agent to create a callback.\n"
            "  → Provide: skillId='4354630', phoneNumber, emailFrom, firstName, lastName, notes.\n"
            "  → After NICE responds, set final=true.\n\n"

            "If urgency==\"non_urgent\" AND proposed_action==\"incident\":\n"
            "  → Ask the Ivanti agent to create an incident.\n"
            "  → Provide: subject, symptom, impact, category, service, owner_team.\n"
            "  → After Ivanti responds, set final=true.\n\n"

            "If you are unsure at all, default to ask_user. "
            "It is always safer to ask than to create a ticket/callback the user didn't want.\n\n"

            "### INVARIANT #3 — Handle User Choice (follow-up turn)\n"
            "When the user replies with '1' or '2' (or equivalent) to the choice prompt:\n"
            "- '1' / 'incident' / 'ticket' → proceed to INVARIANT #4 before calling Ivanti.\n"
            "- '2' / 'callback' / 'call me' → proceed to INVARIANT #4 before calling NICE.\n"
            "- Anything else → Re-ask the same question verbatim. final=false.\n\n"

            "### INVARIANT #4 — Contact info required before any API call\n"
            "Before calling Ivanti or NICE, check the full conversation history for contact info:\n"
            "- **Ivanti incident**: you MUST have the user's corporate email address.\n"
            "- **NICE callback**: you MUST have the user's corporate email AND phone number.\n"
            "If the required contact info is NOT yet in the conversation:\n"
            "  → DO NOT call Ivanti or NICE.\n"
            "  → Set proposed_action='ask_contact' and final=false.\n"
            "  → For an incident, set summary to this EXACT text:\n"
            f'    "{ASK_CONTACT_INCIDENT_PROMPT}"\n'
            "  → For a callback, set summary to this EXACT text:\n"
            f'    "{ASK_CONTACT_CALLBACK_PROMPT}"\n'
            "If the contact info IS present in the conversation (user just replied with it):\n"
            "  → Extract email and phone from the user's reply.\n"
            "  → Proceed to call Ivanti or NICE with those values.\n\n"

            "## IVANTI SERIALIZATION RULE (CRITICAL)\n"
            "When calling the Ivanti agent, every parameter MUST be a plain string.\n"
            "Never pass Semantic Kernel objects or complex types.\n\n"

            "## NICE CALLBACK RULE\n"
            "skillId must be a string: '4354630'.  phoneNumber must be digits only.\n\n"

            "## OUTPUT FORMAT\n"
            "Always return valid JSON:\n"
            "{\n"
            '  "priority": "P1" | "P2" | "P3" | "P4",\n'
            '  "category": "Hardware" | "Software" | "Network" | "Access/Security",\n'
            '  "team": "Infrastructure Team" | "Backend Team" | "Frontend Team" | "Security Team",\n'
            '  "summary": "<user-facing answer or prompt — include ALL steps and image URLs>",\n'
            '  "kb_used": true | false,\n'
            '  "kb_sufficient": true | false,\n'
            '  "urgency": "urgent" | "non_urgent" | "ambiguous" | null,\n'
            '  "proposed_action": "callback" | "incident" | "ask_user" | "kb_answer" | null,\n'
            '  "actions": ["kb_search", ...],\n'
            '  "tool_results": {"ivanti": {...}, "nice": {...}},\n'
            '  "final": true | false\n'
            "}\n\n"
            "When final=true include the word FINAL_RESOLUTION.\n"
            "When final=false your summary MUST contain the verbatim ask-user prompt.\n"
        )

        return ChatCompletionAgent(
            name="Orchestrator",
            instructions=instructions,
            kernel=kernel,
            service=kernel.get_service("chat"),
        )

    def _build_itsm_agent(self) -> ChatCompletionAgent:
        kernel = self._build_kernel()
        kernel.add_plugin(
            ITSMSearchPlugin(
                endpoint=self.config.azure_search_endpoint,
                index_name=self.config.azure_search_index,
                api_key=self.config.azure_search_key,
                content_field=self.config.kb_content_field,
                vision_endpoint=self.config.azure_vision_endpoint,
                vision_key=self.config.azure_vision_key,
            ),
            plugin_name="itsm",
        )
        instructions = (
            "You are the ITSM Knowledge Base agent.\n"
            "When asked to search, use the itsm.search_kb tool.\n"
            "Return the raw JSON results exactly as received.\n"
            "Do NOT fabricate KB content."
        )
        return ChatCompletionAgent(
            name="ITSM",
            instructions=instructions,
            kernel=kernel,
            service=kernel.get_service("chat"),
        )

    def _build_ivanti_agent(self) -> ChatCompletionAgent:
        kernel = self._build_kernel()
        kernel.add_plugin(IvantiPlugin(self.config.ivanti_api_url), plugin_name="ivanti")
        instructions = (
            "You are the Ivanti agent. Use ivanti.create_incident when asked.\n"
            "CRITICAL: All parameters must be plain strings.\n"
            "Return the result JSON (incident number, status, etc.)."
        )
        return ChatCompletionAgent(
            name="Ivanti",
            instructions=instructions,
            kernel=kernel,
            service=kernel.get_service("chat"),
        )

    def _build_nice_agent(self) -> ChatCompletionAgent:
        kernel = self._build_kernel()
        kernel.add_plugin(NICEPlugin(self.config.nice_api_url), plugin_name="nice")
        instructions = (
            "You are the NICE agent. Use nice.create_callback to schedule callbacks.\n"
            "CRITICAL: skillId must be string '4354630'. phoneNumber digits only.\n"
            "Return the result JSON (contactId, status, etc.)."
        )
        return ChatCompletionAgent(
            name="NICE",
            instructions=instructions,
            kernel=kernel,
            service=kernel.get_service("chat"),
        )

    # ------------------------------------------------------------------
    # Parse / extract helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_user_message(response: str) -> str:
        """Extract the user-facing summary from orchestrator output."""
        parsed = MultiAgentOrchestrator._parse_orchestrator_response(response)
        return parsed.get("summary", response)

    @staticmethod
    def _parse_orchestrator_response(response: str) -> dict:
        """Parse orchestrator JSON, handling markdown fences."""
        # Try direct parse
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        # Try extracting from ```json ... ```
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        # Fallback
        return {
            "summary": response,
            "priority": "Unknown",
            "category": "Unknown",
            "team": "Unknown",
            "kb_used": False,
            "kb_sufficient": False,
            "actions": [],
            "final": True,
        }

    # ------------------------------------------------------------------
    # Invariant enforcement (post-LLM)
    # ------------------------------------------------------------------
    def _enforce_invariants(
        self,
        parsed: dict,
        kb_data: dict,
        conversation_id: str,
    ) -> dict:
        """
        Apply non-negotiable invariants AFTER the LLM produces its output.
        Mutates and returns the parsed dict.
        """
        kb_hits = kb_data.get("kb_hits_count", 0)

        # ---- Invariant #1: kb_hits_count==0 → cannot claim KB used ----
        if kb_hits == 0:
            if parsed.get("kb_used") is True or parsed.get("kb_sufficient") is True:
                logger.warning(
                    "Invariant #1 violation: LLM claimed kb_used/kb_sufficient "
                    "but kb_hits_count=0.  Overriding."
                )
                parsed["kb_used"] = False
                parsed["kb_sufficient"] = False

        # ---- Invariant #2: ambiguous → force ask_user, block tools ----
        urgency = parsed.get("urgency", "ambiguous")
        proposed = parsed.get("proposed_action", "ask_user")

        if urgency == "ambiguous" or proposed == "ask_user":
            # Ensure no tool calls slipped through
            tool_results = parsed.get("tool_results", {})
            if tool_results and any(tool_results.values()):
                logger.warning(
                    "Invariant #2 violation: LLM created tool results while "
                    "urgency=ambiguous or proposed_action=ask_user.  Stripping."
                )
                parsed["tool_results"] = {}

            # Force the verbatim ask-user prompt
            parsed["summary"] = ASK_USER_PROMPT
            parsed["final"] = False
            _conversation_states[conversation_id] = ConversationState.WAITING_FOR_CHOICE

        # ---- Invariant #4: ask_contact → block tools, set WAITING_FOR_CONTACT ----
        elif proposed == "ask_contact":
            tool_results = parsed.get("tool_results", {})
            if tool_results and any(tool_results.values()):
                logger.warning(
                    "Invariant #4 violation: LLM created tool results while "
                    "proposed_action=ask_contact.  Stripping."
                )
                parsed["tool_results"] = {}
            parsed["final"] = False
            _conversation_states[conversation_id] = ConversationState.WAITING_FOR_CONTACT
            logger.info(f"Contact info required for conv={conversation_id}; asking user.")

        # ---- Track state for Invariant #3 ----
        if parsed.get("final") is True:
            _conversation_states[conversation_id] = ConversationState.RESOLVED
        elif parsed.get("final") is False and (
            "reply **1** or **2**" in parsed.get("summary", "").lower()
            or "reply with 1 or 2" in parsed.get("summary", "").lower()
            or "1)" in parsed.get("summary", "")
        ):
            _conversation_states[conversation_id] = ConversationState.WAITING_FOR_CHOICE

        return parsed

    # ------------------------------------------------------------------
    # Follow-up detection (Invariant #3)
    # ------------------------------------------------------------------
    @staticmethod
    def _is_followup_choice(user_input: str, conversation_id: str, history) -> bool:
        """
        Detect if the user is replying to a prior 'Reply with 1 or 2' prompt.

        Uses both in-memory state AND history-based heuristic so the
        detection works even if the bot process restarted.
        """
        stripped = user_input.strip().lower()
        choice_tokens = {
            "1", "2", "one", "two", "incident", "callback",
            "create incident", "create callback", "option 1", "option 2",
            "ticket", "call me", "call me back",
        }

        if stripped not in choice_tokens:
            return False

        # Check in-memory state first (fastest)
        if _conversation_states.get(conversation_id) == ConversationState.WAITING_FOR_CHOICE:
            return True

        # Fallback: scan Cosmos history for the ask-user prompt
        if history and history.messages:
            for msg in reversed(history.messages):
                role = getattr(msg, "role", None)
                role_str = role.value if hasattr(role, "value") else str(role or "")
                if "assistant" in role_str.lower():
                    content = msg.content or ""
                    if (
                        "reply **1** or **2**" in content.lower()
                        or "reply with 1 or 2" in content.lower()
                        or "1)" in content
                    ):
                        return True
                    break

        return False

    # ------------------------------------------------------------------
    # Ticket triage (structured / CLI entry point)
    # ------------------------------------------------------------------
    async def run_ticket_triage(
        self, ticket: TicketRequest, conversation_id: str,
        image_bytes: bytes | None = None,
    ) -> TriageResult:
        """
        Full KB-first triage using the hybrid approach.

        1. Pre-search KB → structured JSON
        2. Build context, inject into user message
        3. Run AgentGroupChat (LLM decides)
        4. Enforce invariants on LLM output
        5. Persist & return
        """
        logger.info(f"Triage start: conv={conversation_id}")

        # ---- Step 1: pre-search KB ----
        query = f"{ticket.subject}. {ticket.description}"
        kb_data = self._pre_search_kb(query, image_bytes=image_bytes)
        kb_context = self._build_kb_context(kb_data)

        # ---- Step 2: augmented user message ----
        history = self._history_store.load(conversation_id)
        user_message = (
            f"New ITSM ticket:\n"
            f"Subject: {ticket.subject}\n"
            f"Description: {ticket.description}\n"
            f"Email: {ticket.user_email}\n"
            f"Phone: {ticket.phone_number}\n"
            f"Name: {ticket.user_first_name or ''} {ticket.user_last_name or ''}\n"
        )
        if ticket.additional_context:
            user_message += f"Additional Context: {ticket.additional_context}\n"
        user_message += kb_context
        history.add_user_message(user_message)

        # ---- Step 3: AgentGroupChat ----
        response = await self._run_agent_group_chat(history)

        # ---- Step 4: parse + enforce invariants ----
        parsed = self._parse_orchestrator_response(response)
        parsed = self._enforce_invariants(parsed, kb_data, conversation_id)

        # ---- Step 5: persist ----
        self._history_store.append(conversation_id, "user", user_message)
        self._history_store.append(conversation_id, "assistant", json.dumps(parsed))

        return TriageResult(
            priority=parsed.get("priority", "Unknown"),
            category=parsed.get("category", "Unknown"),
            team=parsed.get("team", "Unknown"),
            orchestrator_summary=parsed.get("summary", ""),
            user_message=parsed.get("summary", response),
            status="success",
            kb_used=parsed.get("kb_used", False),
            kb_hits_count=kb_data.get("kb_hits_count", 0),
            kb_sufficient=parsed.get("kb_sufficient", False),
            kb_results=kb_data.get("results", []),
            actions=parsed.get("actions", []),
            tool_results=parsed.get("tool_results", {}),
            final=parsed.get("final", True),
        )

    # ------------------------------------------------------------------
    # Conversational entry point (Teams bot / chat UI)
    # ------------------------------------------------------------------
    async def run_conversation(
        self, user_input: str, conversation_id: str, image_bytes: bytes | None = None
    ) -> str:
        """
        General conversational entry point.

        - New issues: pre-search KB, inject context, run agentic flow.
        - Follow-ups (user replies 1/2): skip KB search, pass choice directly.
        - Invariants enforced on every response.

        If image_bytes is provided (user attached an image in Teams),
        it is passed to the KB pre-search for Azure Vision vectorizeImage.
        """
        logger.info(
            f"run_conversation: conv={conversation_id}, input={user_input[:80]}..."
            f"{', image=' + str(len(image_bytes)) + ' bytes' if image_bytes else ''}"
        )

        history = self._history_store.load(conversation_id)
        is_followup = self._is_followup_choice(user_input, conversation_id, history)
        is_contact_reply = (
            _conversation_states.get(conversation_id) == ConversationState.WAITING_FOR_CONTACT
        )

        if is_followup:
            # Invariant #3: this is a follow-up choice — no re-search needed
            logger.info(f"Follow-up choice detected: '{user_input.strip()}'")
            history.add_user_message(user_input)
            kb_data = {"kb_hits_count": 0, "results": []}  # N/A for follow-ups

        elif is_contact_reply:
            # Invariant #4: user is supplying their contact info — hint the LLM
            logger.info(f"Contact info reply received for conv={conversation_id}")
            augmented = (
                user_input
                + "\n[User has just provided their contact information above. "
                "Extract the email and phone number from it, then proceed to create "
                "the incident or callback as previously agreed.]"
            )
            history.add_user_message(augmented)
            kb_data = {"kb_hits_count": 0, "results": []}  # N/A for contact replies

        else:
            # New issue: pre-search KB and inject context
            kb_data = self._pre_search_kb(user_input, image_bytes=image_bytes)
            kb_context = self._build_kb_context(kb_data)

            # Let the LLM know an image was attached for search context
            if image_bytes:
                augmented = (
                    user_input
                    + "\n[User attached an image that has been embedded for visual search]"
                    + kb_context
                )
            else:
                augmented = user_input + kb_context

            history.add_user_message(augmented)

        # Run AgentGroupChat
        response = await self._run_agent_group_chat(history)

        # Parse + enforce invariants
        parsed = self._parse_orchestrator_response(response)

        # For follow-ups / contact replies, don't re-enforce KB invariant
        if not is_followup and not is_contact_reply:
            parsed = self._enforce_invariants(parsed, kb_data, conversation_id)
        else:
            # Still enforce state tracking and Invariant #4
            proposed = parsed.get("proposed_action", "")
            if proposed == "ask_contact":
                parsed["final"] = False
                _conversation_states[conversation_id] = ConversationState.WAITING_FOR_CONTACT
            elif parsed.get("final") is True:
                _conversation_states[conversation_id] = ConversationState.RESOLVED

        # Persist
        self._history_store.append(conversation_id, "user", user_input)
        self._history_store.append(conversation_id, "assistant", response)

        return parsed.get("summary", response)

    # ------------------------------------------------------------------
    # Agent group chat runner (shared by both entry points)
    # ------------------------------------------------------------------
    async def _run_agent_group_chat(self, history) -> str:
        """Run AgentGroupChat and return the last Orchestrator response."""
        chat = AgentGroupChat(
            agents=[
                self._orchestrator_agent,
                self._itsm_agent,
                self._ivanti_agent,
                self._nice_agent,
            ],
            termination_strategy=FinalResolutionTerminationStrategy(),
            chat_history=history,
        )

        response = ""
        try:
            async for message in chat.invoke():
                response = message.content or ""
                logger.info(f"Agent [{message.name}]: {response[:200]}...")
        except Exception as e:
            # Tool call safety: failures never crash the orchestration
            logger.error(f"AgentGroupChat error: {e}", exc_info=True)
            response = json.dumps({
                "summary": (
                    "I encountered a temporary issue processing your request. "
                    "Please try again or contact the help desk directly."
                ),
                "priority": "Unknown",
                "category": "Unknown",
                "team": "Unknown",
                "kb_used": False,
                "kb_sufficient": False,
                "actions": [],
                "tool_results": {},
                "final": True,
                "status": "failed",
                "error": str(e),
            })

        return response


# ---------------------------------------------------------------------------
# Sync entry point for CLI
# ---------------------------------------------------------------------------
def run_ticket(ticket: TicketRequest, conversation_id: str) -> TriageResult:
    orchestrator = MultiAgentOrchestrator()
    return asyncio.run(orchestrator.run_ticket_triage(ticket, conversation_id))
