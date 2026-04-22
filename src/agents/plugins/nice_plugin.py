"""
NICE inContact API Plugin (aiohttp)

JSON Serialization Fix:
- All parameters are explicitly converted to plain Python types
  before building the HTTP payload.
- Reuses _to_plain_str() to safely unwrap Semantic Kernel wrapper objects.
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
from semantic_kernel.functions import kernel_function

logger = logging.getLogger(__name__)


def _to_plain_str(value: Any) -> str:
    """Convert any value (including SK wrapper types) to a plain Python str."""
    if value is None:
        return ""
    if type(value) is str:
        return value
    for attr in ("value", "content", "result"):
        inner = getattr(value, attr, None)
        if inner is not None and isinstance(inner, str):
            return inner
    return str(value)


class NICEPlugin:
    """Semantic Kernel plugin for NICE inContact actions."""

    def __init__(self, api_url: str, timeout: int = 30):
        self._api_url = api_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    def _clean_phone(self, phone: str) -> str:
        cleaned = "".join(ch for ch in phone if ch.isdigit())
        return cleaned if len(cleaned) >= 10 else "9999999999"

    @kernel_function(name="create_callback", description="Create a callback request in NICE inContact.")
    async def create_callback(
        self,
        skillId: str,
        phoneNumber: str,
        emailFrom: str,
        firstName: str = "",
        lastName: str = "",
        notes: str = "",
        priority: int = 5,
        mediaType: int = 4,
        emailBccAddress: str | None = None,
    ) -> dict[str, Any]:
        """
        Create callback request in NICE inContact.

        Every parameter is forced to its expected plain type before building
        the JSON payload, preventing serialization errors from SK objects.
        """
        # ---- Robust type conversion ----
        try:
            skillId_str = _to_plain_str(skillId)
            phoneNumber_str = self._clean_phone(_to_plain_str(phoneNumber))
            emailFrom_str = _to_plain_str(emailFrom)
            firstName_str = _to_plain_str(firstName)
            lastName_str = _to_plain_str(lastName)
            notes_str = _to_plain_str(notes)
            emailBccAddress_str = _to_plain_str(emailBccAddress) or emailFrom_str

            # priority/mediaType may arrive as str from the LLM
            try:
                priority_int = int(priority) if priority is not None else 5
            except (ValueError, TypeError):
                priority_int = 5
            try:
                mediaType_int = int(mediaType) if mediaType is not None else 4
            except (ValueError, TypeError):
                mediaType_int = 4

        except Exception as e:
            logger.error(f"Type conversion error: {e}")
            return {"success": False, "error": f"Invalid parameter types: {e}"}

        payload = {
            "skillId": skillId_str,
            "mediaType": mediaType_int,
            "workItemQueueType": None,
            "isActive": True,
            "phoneNumber": phoneNumber_str,
            "emailFromEditable": True,
            "emailFrom": emailFrom_str,
            "emailBccAddress": emailBccAddress_str,
            "firstName": firstName_str,
            "lastName": lastName_str,
            "priority": priority_int,
            "targetAgentId": None,
            "notes": notes_str,
        }

        url = f"{self._api_url}/callback-queue"
        logger.info("NICE request: %s", url)

        try:
            async with aiohttp.ClientSession(timeout=self._timeout) as session:
                async with session.post(url, json=payload) as response:
                    text = await response.text()
                    if response.status >= 400:
                        logger.error("NICE HTTP %s: %s", response.status, text[:500])
                        return {"success": False, "status_code": response.status, "error": text}
                    try:
                        data = await response.json()
                    except Exception:
                        data = {"raw": text}

            return {
                "success": True,
                "contact_id": data.get("contactId"),
                "message": data.get("message"),
                "full_response": data,
            }
        except Exception as e:
            logger.error(f"NICE API call failed: {e}")
            return {"success": False, "error": str(e)}
