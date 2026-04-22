"""
ITSM Policy Classifier

Encodes ITSM KB policy rules for:
- Priority classification (P1-P4)
- Category and team assignment
- Confidence-based auto-escalation gating
- Urgency detection

Auto-escalation gate:
  Auto-callback ONLY when priority is P1/P2 AND classifier confidence
  is at or above AUTO_ESCALATE_CONFIDENCE_THRESHOLD (default 0.75).
  If urgency/intent is ambiguous at ANY priority, the gate returns
  ASK_USER so the user is always prompted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


# ---------------------------------------------------------------------------
# Threshold: minimum confidence required to auto-create a callback.
# Below this → always ask the user even if priority appears high.
# ---------------------------------------------------------------------------
AUTO_ESCALATE_CONFIDENCE_THRESHOLD: float = 0.75


@dataclass
class ClassificationResult:
    """Result of ITSM policy classification"""
    priority: Literal["P1", "P2", "P3", "P4"]
    category: Literal["Hardware", "Software", "Network", "Access/Security"]
    team: str
    urgency_level: Literal["critical", "high", "medium", "low"]

    # Confidence scores (0.0 – 1.0)
    priority_confidence: float
    category_confidence: float
    overall_confidence: float

    # Deterministic escalation gate
    auto_escalate: bool  # True = create callback automatically
    escalation_gate: Literal["AUTO_ESCALATE", "ASK_USER"]


class ITSMPolicyClassifier:
    """Classifies tickets based on ITSM KB policy rules"""

    # ---- Priority keywords (from ITSM KB policy document) ----
    P1_KEYWORDS = [
        "down", "outage", "complete", "critical", "production", "all users",
        "system failure", "cannot work", "urgent", "emergency", "asap",
        "broken", "crashed", "not working at all", "entire", "whole",
    ]

    P2_KEYWORDS = [
        "intermittent", "slow", "degraded", "partial", "multiple users",
        "important", "high priority", "affecting team", "major",
        "can't connect", "cannot access", "blocked",
    ]

    P3_KEYWORDS = [
        "single user", "individual", "minor", "one person", "my",
        "password reset", "access request", "help with",
    ]

    P4_KEYWORDS = [
        "request", "enhancement", "feature", "cosmetic", "question",
        "inquiry", "information", "how to", "documentation",
    ]

    # ---- Category keywords ----
    HARDWARE_KEYWORDS = [
        "laptop", "desktop", "computer", "workstation", "server",
        "printer", "monitor", "keyboard", "mouse", "hardware",
        "physical", "device", "equipment",
    ]

    SOFTWARE_KEYWORDS = [
        "application", "app", "software", "program", "install",
        "license", "error message", "crash", "bug", "update",
        "excel", "word", "outlook", "browser", "chrome",
    ]

    NETWORK_KEYWORDS = [
        "vpn", "network", "connectivity", "connection", "internet",
        "wifi", "wireless", "firewall", "dns", "bandwidth",
        "slow connection", "cannot connect", "timeout",
    ]

    SECURITY_KEYWORDS = [
        "login", "password", "account", "access", "permission",
        "locked out", "cannot login", "security", "unauthorized",
        "mfa", "2fa", "authentication", "credentials",
    ]

    # ---- Team assignments ----
    TEAM_MAP = {
        "Hardware": "Infrastructure Team",
        "Software": "Backend Team",
        "Network": "Infrastructure Team",
        "Access/Security": "Security Team",
    }

    # ------------------------------------------------------------------
    def classify(self, subject: str, description: str) -> ClassificationResult:
        """
        Classify ticket and compute the deterministic escalation gate.

        Returns ClassificationResult with:
          - priority, category, team
          - priority_confidence, category_confidence, overall_confidence
          - auto_escalate (bool), escalation_gate ("AUTO_ESCALATE" | "ASK_USER")
        """
        text = f"{subject} {description}".lower()

        priority, urgency, priority_confidence = self._classify_priority(text)
        category, category_confidence = self._classify_category(text)
        team = self.TEAM_MAP.get(category, "Backend Team")

        overall_confidence = (priority_confidence + category_confidence) / 2.0

        auto_escalate = self._should_auto_escalate(
            priority, urgency, priority_confidence
        )
        escalation_gate: Literal["AUTO_ESCALATE", "ASK_USER"] = (
            "AUTO_ESCALATE" if auto_escalate else "ASK_USER"
        )

        return ClassificationResult(
            priority=priority,
            category=category,
            team=team,
            urgency_level=urgency,
            priority_confidence=priority_confidence,
            category_confidence=category_confidence,
            overall_confidence=overall_confidence,
            auto_escalate=auto_escalate,
            escalation_gate=escalation_gate,
        )

    # ------------------------------------------------------------------
    # Priority classification
    # ------------------------------------------------------------------
    def _classify_priority(self, text: str) -> tuple[str, str, float]:
        """
        Returns (priority, urgency_level, confidence).
        """
        p1_score = sum(1 for kw in self.P1_KEYWORDS if kw in text)
        p2_score = sum(1 for kw in self.P2_KEYWORDS if kw in text)
        p3_score = sum(1 for kw in self.P3_KEYWORDS if kw in text)
        p4_score = sum(1 for kw in self.P4_KEYWORDS if kw in text)

        scores = {
            "P1": (p1_score, "critical"),
            "P2": (p2_score, "high"),
            "P3": (p3_score, "medium"),
            "P4": (p4_score, "low"),
        }

        max_priority = max(scores.items(), key=lambda x: x[1][0])
        priority = max_priority[0]
        urgency = max_priority[1][1]

        total_matches = p1_score + p2_score + p3_score + p4_score
        if total_matches == 0:
            return "P3", "medium", 0.3

        confidence = max_priority[1][0] / total_matches

        # Boost when there are multiple strong P1 indicators
        if p1_score >= 2:
            confidence = min(1.0, confidence + 0.2)

        return priority, urgency, round(confidence, 4)

    # ------------------------------------------------------------------
    # Category classification
    # ------------------------------------------------------------------
    def _classify_category(self, text: str) -> tuple[str, float]:
        """Returns (category, confidence)."""
        hw_score = sum(1 for kw in self.HARDWARE_KEYWORDS if kw in text)
        sw_score = sum(1 for kw in self.SOFTWARE_KEYWORDS if kw in text)
        net_score = sum(1 for kw in self.NETWORK_KEYWORDS if kw in text)
        sec_score = sum(1 for kw in self.SECURITY_KEYWORDS if kw in text)

        scores = {
            "Hardware": hw_score,
            "Software": sw_score,
            "Network": net_score,
            "Access/Security": sec_score,
        }

        max_category = max(scores.items(), key=lambda x: x[1])
        category = max_category[0]

        total_matches = hw_score + sw_score + net_score + sec_score
        if total_matches == 0:
            return "Software", 0.3

        confidence = max_category[1] / total_matches
        return category, round(confidence, 4)

    # ------------------------------------------------------------------
    # Confidence-based auto-escalation gate
    # ------------------------------------------------------------------
    @staticmethod
    def _should_auto_escalate(
        priority: str,
        urgency: str,
        priority_confidence: float,
    ) -> bool:
        """
        Decide whether to auto-create a NICE callback.

        Auto-escalation ONLY happens when ALL of:
          1. Priority is P1 or P2
          2. Classifier confidence ≥ AUTO_ESCALATE_CONFIDENCE_THRESHOLD

        If urgency/intent is ambiguous (low confidence), we always ask
        the user regardless of priority level.
        """
        if priority not in ("P1", "P2"):
            return False
        return priority_confidence >= AUTO_ESCALATE_CONFIDENCE_THRESHOLD
