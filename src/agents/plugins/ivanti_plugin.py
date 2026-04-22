"""
Ivanti API Plugin (aiohttp)

JSON Serialization Fix:
- All parameters are explicitly converted to plain Python strings
  before building the HTTP payload.
- AzureChatCompletion objects, FunctionResult wrappers, and any other
  Semantic Kernel types are safely converted via _to_plain_str().

Parameter naming note:
- The IT service field is intentionally named `it_service` (not `service`).
  Semantic Kernel reserves the name `service` for its own dependency injection
  and will inject the kernel's chat-completion service object if a function
  parameter is literally called `service`.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

import aiohttp
from semantic_kernel.functions import kernel_function

logger = logging.getLogger(__name__)


def _to_plain_str(value: Any) -> str:
    """
    Convert *any* value to a plain Python str.

    Handles Semantic Kernel objects (AzureChatCompletion results,
    FunctionResult, ChatMessageContent, etc.) that are NOT JSON-
    serializable by extracting their text representation first.
    """
    if value is None:
        return ""
    # Already a plain str → fast path
    if type(value) is str:
        return value
    # If it has a .value or .content attribute (SK wrapper types), unwrap
    for attr in ("value", "content", "result"):
        inner = getattr(value, attr, None)
        if inner is not None and isinstance(inner, str):
            return inner
    # Fall back to str()
    return str(value)


class IvantiPlugin:
    """Semantic Kernel plugin for Ivanti incident actions."""

    def __init__(self, api_url: str, timeout: int = 30):
        self._api_url = api_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    @kernel_function(
        name="create_incident",
        description=(
            "Create an IT support incident in Ivanti ITSM. "
            "Use this when the user wants to report a technical problem or request IT help. "
            "Map the user's issue to the correct incident_type and other required enum fields."
        ),
    )
    async def create_incident(
        self,
        email: Annotated[str, "Employee's corporate email address (e.g. user@company.com)"],
        subject: Annotated[str, "Short one-line summary of the issue"],
        symptom: Annotated[str, "Full detailed description of what the user is experiencing"],
        incident_type: Annotated[
            str,
            (
                "Type of incident — must be exactly one of: "
                "'FDR Issues', 'FWS Issues', 'Laptop Issues', 'Outlook Issues', "
                "'PIPS Issues', 'Portal Access Missing', 'Portal Logon Issue', "
                "'Portal Other Issue', 'RSA Soft Token Setup for New Phone', "
                "'Windows 11 Upgrade Question or Issue', 'Cisco VPN Issues', "
                "'Account Passwords Not Synchronized', "
                "'Account  Smart Card Blocked (PIV / CAC)'. "
                "Choose the closest match to the user's issue. "
                "Login/password problems → 'Portal Logon Issue'. "
                "VPN problems → 'Cisco VPN Issues'. "
                "Laptop hardware → 'Laptop Issues'. "
                "Email client → 'Outlook Issues'."
            ),
        ],
        urgency: Annotated[
            str,
            "Urgency level — must be exactly one of: 'Low', 'Medium', 'High'.",
        ] = "Medium",
        impact: Annotated[
            str,
            "Business impact level — must be exactly one of: 'Low', 'Medium', 'High', 'Critical'.",
        ] = "Medium",
        it_service: Annotated[
            str,
            (
                "IT service category — must be exactly one of: "
                "'Software', 'Hardware', 'Network', 'Support'. "
                "Login/app issues → 'Software'. "
                "VPN/connectivity → 'Network'. "
                "Physical device/peripherals → 'Hardware'. "
                "General help-desk request → 'Support'."
            ),
        ] = "Support",
        category: Annotated[
            str,
            (
                "Issue category — must be exactly one of: "
                "'Zoom', 'Windows', 'Outlook', 'Adobe Acrobat', 'Other'. "
                "Choose the closest match; use 'Other' when unsure."
            ),
        ] = "Other",
        source: Annotated[
            str,
            "Channel the request came from. Default: 'Instant Message'.",
        ] = "Instant Message",
    ) -> dict[str, Any]:
        """
        Create incident in Ivanti ITSM.

        IMPORTANT: Every parameter is forced to a plain Python string before
        the JSON payload is built, preventing serialization errors when
        Semantic Kernel passes wrapped objects.

        NOTE: The IT service field is named `it_service` (not `service`) to
        avoid Semantic Kernel's built-in dependency injection which hijacks
        any function parameter literally named `service`.
        """
        # ---- Robust type conversion ----
        try:
            email_str     = _to_plain_str(email)
            subject_str   = _to_plain_str(subject)
            symptom_str   = _to_plain_str(symptom)
            type_str      = _to_plain_str(incident_type)
            urgency_str   = _to_plain_str(urgency) or "Medium"
            impact_str    = _to_plain_str(impact) or "Medium"
            category_str  = _to_plain_str(category) or "Other"
            service_str   = _to_plain_str(it_service) or "Support"
            source_str    = _to_plain_str(source) or "Instant Message"
        except Exception as e:
            logger.error(f"Type conversion error: {e}")
            return {"success": False, "error": f"Invalid parameter types: {e}"}

        # ---- Validate required strings ----
        for param_name, param_value in [
            ("email",         email_str),
            ("subject",       subject_str),
            ("symptom",       symptom_str),
            ("incident_type", type_str),
            ("impact",        impact_str),
            ("category",      category_str),
            ("it_service",    service_str),
        ]:
            if not isinstance(param_value, str):
                return {
                    "success": False,
                    "error": f"{param_name} must be a string, got {type(param_value)}",
                }

        # ---- Build plain-dict payload matching IncidentRequest model ----
        payload = {
            "email":         email_str,
            "subject":       subject_str,
            "symptom":       symptom_str,
            "incident_type": type_str,
            "urgency":       urgency_str,
            "impact":        impact_str,
            "category":      category_str,
            "service":       service_str,   # API field is still "service"
            "source":        source_str,
        }

        url = f"{self._api_url}/incidents"
        logger.info("Ivanti request: %s  payload_keys=%s", url, list(payload.keys()))

        try:
            async with aiohttp.ClientSession(timeout=self._timeout) as session:
                async with session.post(url, json=payload) as response:
                    text = await response.text()
                    if response.status >= 400:
                        logger.error("Ivanti HTTP %s: %s", response.status, text[:500])
                        return {"success": False, "status_code": response.status, "error": text}
                    try:
                        data = await response.json()
                    except Exception:
                        data = {"raw": text}

            return {
                "success": True,
                "incident_id": data.get("incident_id"),
                "incident_number": (data.get("data") or {}).get("IncidentNumber"),
                "message": data.get("message"),
                "full_response": data,
            }
        except Exception as e:
            logger.error(f"Ivanti API call failed: {e}")
            return {"success": False, "error": str(e)}
