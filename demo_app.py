"""
ITSM AI Assistant — Streamlit Demo
====================================
Run:   streamlit run demo_app.py
Logo:  drop  peraton_logo.png  in this folder to display it in the navbar.
"""

from __future__ import annotations

import asyncio
import base64
import json as _json
import re as _re
import sys
import uuid
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ── add src/ to Python path ─────────────────────────────────────────────────
_SRC = Path(__file__).parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from agents.multi_agent_orchestrator import MultiAgentOrchestrator, TicketRequest

# ── page config  (must be the first Streamlit call) ─────────────────────────
st.set_page_config(
    page_title="ITSM AI Assistant",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ──────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
      /* Hide default Streamlit header / footer */
      #MainMenu, header, footer { visibility: hidden; height: 0; }
      .block-container {
        padding-top: 0 !important;
        max-width: 1200px;
      }

      /* ── Navbar ── */
      .rdg-navbar {
        background: #000000;
        color: white;
        padding: 14px 28px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin: -20px -2rem 28px -2rem;
        border-bottom: 1px solid #222;
      }
      .rdg-navbar-left  { display: flex; align-items: center; gap: 16px; }
      .rdg-navbar-title { font-size: 20px; font-weight: 700; color: white; letter-spacing: -.3px; }
      .rdg-navbar-sub   { font-size: 12px; color: rgba(255,255,255,.55); margin-top: 2px; }
      .rdg-live-badge   {
        background: rgba(255,255,255,.1);
        border: 1px solid rgba(255,255,255,.2);
        color: white;
        padding: 5px 14px;
        border-radius: 20px;
        font-size: 12px;
        letter-spacing: .04em;
      }
      .rdg-live-dot {
        display: inline-block;
        width: 7px; height: 7px;
        background: #22c55e;
        border-radius: 50%;
        margin-right: 6px;
        animation: blink 1.8s ease-in-out infinite;
      }
      @keyframes blink { 0%,100% { opacity:1; } 50% { opacity:.3; } }

      /* ── Sidebar ── */
      [data-testid="stSidebar"] { background: #0d0d0d !important; }
      [data-testid="stSidebar"] label,
      [data-testid="stSidebar"] .stMarkdown p,
      [data-testid="stSidebar"] .stMarkdown h3 { color: #e5e7eb !important; }
      [data-testid="stSidebar"] .stTextInput > div > input {
        background: #1a1a1a !important;
        border: 1px solid #333 !important;
        color: white !important;
        border-radius: 8px !important;
      }
      [data-testid="stSidebar"] .stTextInput > div > input::placeholder { color: #555 !important; }

      /* ── Chat bubbles ── */
      [data-testid="stChatMessage"] { border-radius: 12px !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Navbar ───────────────────────────────────────────────────────────────────
_LOGO = Path(__file__).parent / "peraton_logo.png"
if _LOGO.exists():
    _b64 = base64.b64encode(_LOGO.read_bytes()).decode()
    logo_html = f'<img src="data:image/png;base64,{_b64}" height="38" alt="Peraton" />'
else:
    logo_html = '<span style="font-size:26px;line-height:1">🛡️</span>'

st.markdown(
    f"""
    <div class="rdg-navbar">
      <div class="rdg-navbar-left">
        {logo_html}
        <div>
          <div class="rdg-navbar-title">ITSM AI Assistant</div>
          <div class="rdg-navbar-sub">Peraton RDG &nbsp;·&nbsp; Azure OpenAI &amp; Semantic Kernel</div>
        </div>
      </div>
      <div class="rdg-live-badge">
        <span class="rdg-live-dot"></span>Live Demo
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ── Reply cleaner ────────────────────────────────────────────────────────────
def _clean_bot_reply(text: str) -> str:
    """
    Post-process every bot reply before display:

    1. Raw-JSON guard — if the LLM returned its decision JSON without a
       'summary' field, extract one or build a sensible fallback so the
       user never sees a wall of JSON.

    2. Image-link fallback — blob.core.usgovcloudapi.net images require
       VPN / SAS auth and won't render in a local browser.  Convert
       ![alt](url) → [🖼️ alt](url) so they appear as clickable links.
    """
    stripped = text.strip()

    # ── 1. Raw JSON guard ────────────────────────────────────────────────────
    if stripped.startswith("{"):
        try:
            d = _json.loads(stripped)
            summary = d.get("summary") or d.get("answer") or ""

            if not summary:
                # Build a friendly fallback from the decision fields
                tr       = d.get("tool_results") or {}
                ivanti   = tr.get("ivanti") or {}
                nice     = tr.get("nice")   or {}
                action   = d.get("proposed_action", "")

                if ivanti.get("success"):
                    inc = (ivanti.get("full_response") or {})
                    inc = (inc.get("incident_data") or {}).get("IncidentNumber", "")
                    summary = (
                        f"✅ Your support ticket has been created.\n\n"
                        f"**Incident Number:** {inc}\n\n"
                        "The IT team will be in touch shortly. "
                        "Let me know if you need anything else!"
                    )
                elif nice.get("success"):
                    summary = (
                        "✅ A callback has been scheduled for you.\n\n"
                        "A support specialist will call you back shortly."
                    )
                elif action in ("callback", "incident", "ask_user"):
                    summary = (
                        "I wasn't able to find a direct answer in our knowledge base "
                        "— but I can still help!\n\n"
                        "**1)** Create an incident — logs your issue and assigns it "
                        "to the right team.\n\n"
                        "**2)** Request a callback — a specialist will call you back.\n\n"
                        "Reply **1** or **2** and I'll take care of it!"
                    )
                else:
                    summary = (
                        "I've reviewed your request. "
                        "Reply **1** for a support ticket or **2** for a callback."
                    )

            text = summary
        except (_json.JSONDecodeError, AttributeError):
            pass  # Not valid JSON — display as-is

    # ── 2. Image-link fallback ───────────────────────────────────────────────
    # ![alt text](https://...) → [🖼️ alt text](https://...)
    text = _re.sub(
        r"!\[([^\]]*)\]\((https?://[^)]+)\)",
        r"[🖼️ \1](\2)",
        text,
    )

    return text


# ── Orchestrator singleton (cached across reruns) ─────────────────────────────
@st.cache_resource(show_spinner="Initialising AI engine…")
def get_orchestrator() -> MultiAgentOrchestrator:
    return MultiAgentOrchestrator()


# ── Async helper (safe for Streamlit's thread model) ─────────────────────────
def run_async(coro):
    """Run an async coroutine from synchronous Streamlit code."""
    try:
        # If no event loop is running just use asyncio.run()
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    # An event loop IS running (e.g., inside Streamlit's thread).
    # Spin up a fresh thread to avoid "This event loop is already running".
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, coro)
        return future.result()


# ── Session-state defaults ─────────────────────────────────────────────────
for _k, _v in {
    "messages": [],
    "conv_id": None,
    "triage": None,
}.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ── Sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 👤 Your Information")
    email = st.text_input("Email address", placeholder="you@peraton.com", key="email")
    phone = st.text_input("Phone number",  placeholder="+1 (555) 000-0000", key="phone")

    st.divider()

    if st.button("✏️  New Conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.conv_id  = None
        st.session_state.triage   = None
        st.rerun()

    # ── Triage metadata ──────────────────────────────────────────────────────
    t = st.session_state.triage
    if t:
        st.divider()
        st.markdown("### 📊 Triage Result")
        c1, c2 = st.columns(2)
        c1.metric("Priority", t.get("priority") or "—")
        c2.metric("KB Hits",  t.get("kb_hits", 0))
        st.markdown(f"**Category:** {t.get('category') or '—'}")
        st.markdown(f"**Team:** {t.get('team') or '—'}")

        actions = t.get("actions") or []
        if actions:
            st.divider()
            st.markdown("### ✅ Actions Taken")
            for a in actions:
                st.markdown(f"- {a.replace('_', ' ').title()}")

        tr = t.get("tool_results") or {}
        if any(tr.values()):
            st.divider()
            st.markdown("### 🔧 Tickets / Callbacks")
            if tr.get("ivanti"):
                st.success("Ivanti incident created")
            if tr.get("nice"):
                st.info("Callback queued with NICE")


# ── Chat area ────────────────────────────────────────────────────────────────
# Render history
for msg in st.session_state.messages:
    avatar = "🤖" if msg["role"] == "assistant" else "👤"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])

# Welcome message on first load
if not st.session_state.messages:
    with st.chat_message("assistant", avatar="🤖"):
        st.markdown(
            "👋 Hi! I'm your ITSM AI Assistant.\n\n"
            "Describe your IT issue and I'll search our knowledge base, "
            "create a support ticket, or arrange a callback — whichever fits best.\n\n"
            "**Try something like:**\n"
            "- *My VPN isn't connecting*\n"
            "- *Outlook keeps crashing since the last update*\n"
            "- *I have a login issue — please call me back*\n"
            "- *How do I set up RSA Soft Token on a new phone?*"
        )

# ── Input & response ─────────────────────────────────────────────────────────
placeholder = (
    "Reply here…  (type 1 for incident · 2 for callback)"
    if st.session_state.conv_id
    else "Describe your IT issue…"
)

if prompt := st.chat_input(placeholder):

    # Show user bubble immediately
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Get AI response
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("Thinking…"):
            try:
                orch = get_orchestrator()

                if not st.session_state.conv_id:
                    # ── First turn: full KB-first triage ──────────────────
                    conv_id = str(uuid.uuid4())
                    st.session_state.conv_id = conv_id

                    ticket = TicketRequest(
                        subject=prompt[:100],
                        description=prompt,
                        user_email=email or "demo@peraton.com",
                        phone_number=phone or "+10000000000",
                    )
                    result = run_async(orch.run_ticket_triage(ticket, conv_id))

                    reply = _clean_bot_reply(
                        result.user_message or result.orchestrator_summary or "(no response)"
                    )

                    # Cache metadata for sidebar
                    st.session_state.triage = {
                        "priority":     result.priority,
                        "category":     result.category,
                        "team":         result.team,
                        "kb_used":      result.kb_used,
                        "kb_hits":      result.kb_hits_count,
                        "actions":      result.actions,
                        "tool_results": result.tool_results,
                    }

                else:
                    # ── Follow-up turn (handles "1", "2", etc.) ───────────
                    # Always re-attach contact info so the LLM can pass it
                    # directly to Ivanti / NICE without hunting through history.
                    _user_email = email or st.session_state.get("email") or "demo@peraton.com"
                    _user_phone = phone or st.session_state.get("phone") or "+10000000000"
                    followup_input = (
                        f"{prompt}\n"
                        f"[User contact: email={_user_email}, phone={_user_phone}]"
                    )
                    reply = _clean_bot_reply(
                        run_async(
                            orch.run_conversation(
                                user_input=followup_input,
                                conversation_id=st.session_state.conv_id,
                            )
                        )
                    )

                st.markdown(reply)
                st.session_state.messages.append({"role": "assistant", "content": reply})

            except Exception as exc:
                err = f"⚠️ **Error:** {exc}"
                st.error(str(exc))
                st.session_state.messages.append({"role": "assistant", "content": err})

    st.rerun()
