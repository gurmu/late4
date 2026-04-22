"""
Refactored Multi-Agent Orchestrator with KB-First Logic

NOTE: Due to the complexity of completely refactoring run_ticket_triage,
this file contains the new implementation that should REPLACE the existing method.
"""

# New imports needed
from agents.itsm_policy_classifier import ITSMPolicyClassifier, ClassificationResult

# Add to __init__ method:
# self._policy_classifier = ITSMPolicyClassifier()

# ============================================================================
# REPLACEMENT METHOD FOR run_ticket_triage
# ============================================================================

async def run_ticket_triage(self, ticket: TicketRequest, conversation_id: str) -> TriageResult:
    """
    KB-First Triage Flow with ITSM Policy Classification
    
    Flow:
    1. Query KB first
    2. If KB has results → Return answer (STOP)
    3. If no KB results → Classify using ITSM policy
    4. Based on priority/urgency → Create ticket OR ask user
    """
    logger.info(f"Starting KB-first triage for conversation: {conversation_id}")
    
    # Track all actions
    actions = []
    tool_results = {"ivanti": {"status": "skipped"}, "nice": {"status": "skipped"}}
    
    # Step 1: Query ITSM Knowledge Base FIRST
    kb_result = await self._query_kb(ticket.subject, ticket.description)
    actions.append({
        "action": "kb_search",
        "status": "success" if kb_result["hits_count"] > 0 else "no_results",
        "error": None
    })
    
    # Step 2: If KB has relevant results → STOP and return answer
    if kb_result["hits_count"] > 0 and kb_result["best_score"] >= 0.7:
        logger.info(f"KB returned {kb_result['hits_count']} results. Stopping triage.")
        
        # Generate answer from KB results
        summary = self._generate_kb_answer(kb_result["results"])
        
        # Classify for metadata (priority/category/team) but don't escalate
        classification = self._policy_classifier.classify(ticket.subject, ticket.description)
        
        return TriageResult(
            priority=classification.priority,
            category=classification.category,
            team=classification.team,
            orchestrator_summary=summary,
            kb_used=True,
            kb_hits_count=kb_result["hits_count"],
            kb_results=kb_result["results"],
            actions=actions,
            tool_results=tool_results,
            status="success",
        )
    
    # Step 3: No KB results → Classify using ITSM policy
    logger.info("No KB results. Classifying ticket using ITSM policy...")
    classification = self._policy_classifier.classify(ticket.subject, ticket.description)
    
    actions.append({
        "action": "itsm_classification",
        "status": "success",
        "data": {
            "priority": classification.priority,
            "urgency": classification.urgency_level,
            "confidence": classification.confidence,
        },
        "error": None,
    })
    
    # Step 4: Decide escalation based on ITSM policy
    summary = f"Ticket classified as {classification.priority} ({classification.urgency_level} urgency). "
    
    # P1 (Critical) → Always create callback
    if classification.priority == "P1":
        logger.info("P1 Critical - Creating NICE callback automatically")
        nice_result = await self._safe_create_callback(ticket, classification, conversation_id)
        tool_results["nice"] = nice_result
        actions.append({"action": "create_callback", "status": nice_result["status"], "error": nice_result.get("error")})
        summary += "NICE callback created for immediate response (P1 SLA: 15min response)."
    
    # P2 (High) → Create callback (default for high priority)
    elif classification.priority == "P2":
        logger.info("P2 High - Creating NICE callback for high priority issue")
        nice_result = await self._safe_create_callback(ticket, classification, conversation_id)
        tool_results["nice"] = nice_result
        actions.append({"action": "create_callback", "status": nice_result["status"], "error": nice_result.get("error")})
        summary += "NICE callback created for high-priority issue (P2 SLA: 1hr response)."
    
    # P3 (Medium) → Create Ivanti incident for tracking
    elif classification.priority == "P3":
        logger.info("P3 Medium - Creating Ivanti incident for tracking")
        ivanti_result = await self._safe_create_incident(ticket, classification, conversation_id)
        tool_results["ivanti"] = ivanti_result
        actions.append({"action": "create_incident", "status": ivanti_result["status"], "error": ivanti_result.get("error")})
        summary += "Ivanti incident created for tracking (P3 SLA: 4hr response, 24hr resolution)."
    
    # P4 (Low) → Just log, no automatic escalation
    else:
        logger.info("P4 Low - No automatic escalation")
        summary += "Low priority request logged. No immediate action required (P4 SLA: 8hr response)."
    
    return TriageResult(
        priority=classification.priority,
        category=classification.category,
        team=classification.team,
        orchestrator_summary=summary,
        kb_used=False,
        kb_hits_count=0,
        kb_results=[],
        actions=actions,
        tool_results=tool_results,
        status="success",
    )


# ============================================================================
# HELPER METHODS (add to MultiAgentOrchestrator class)
# ============================================================================

async def _query_kb(self, subject: str, description: str) -> dict:
    """
    Query ITSM KB and return structured results
    
    Returns:
        {
            "hits_count": int,
            "best_score": float,
            "results": [{"content": str, "score": float}, ...],
        }
    """
    try:
        query = f"{subject}. {description}"
        
        # Create temporary kernel with ITSM plugin
        kernel = self._build_kernel()
        kernel.add_plugin(
            ITSMSearchPlugin(
                endpoint=self.config.azure_search_endpoint,
                index_name=self.config.azure_search_index,
                api_key=self.config.azure_search_key,
                content_field=self.config.kb_content_field,
            ),
            plugin_name="itsm",
        )
        
        # Get search function and invoke
        search_func = kernel.get_function("itsm", "search_kb")
        result = await search_func.invoke(kernel, query=query, top_k=self.config.kb_top_k)
        
        # Parse result (assuming it returns list of docs)
        # This is simplified - adjust based on actual plugin response format
        results = []
        if result and result.value:
            # Handle different response formats
            if isinstance(result.value, list):
                results = [{"content": str(r), "score": 1.0} for r in result.value]
            elif isinstance(result.value, str):
                results = [{"content": result.value, "score": 1.0}]
        
        return {
            "hits_count": len(results),
            "best_score": results[0]["score"] if results else 0.0,
            "results": results,
        }
    except Exception as e:
        logger.error(f"KB search failed: {e}")
        return {"hits_count": 0, "best_score": 0.0, "results": []}


def _generate_kb_answer(self, kb_results: list[dict]) -> str:
    """Generate user-friendly answer from KB results"""
    if not kb_results:
        return "No relevant KB articles found."
    
    # Take top result
    top_result = kb_results[0]["content"]
    summary = f"Based on ITSM Knowledge Base:\\n\\n{top_result[:500]}"
    
    if len(kb_results) > 1:
        summary += f"\\n\\n({len(kb_results)} related articles found)"
    
    return summary


async def _safe_create_incident(
    self, ticket: TicketRequest, classification: ClassificationResult, conversation_id: str
) -> dict:
    """Safely create Ivanti incident with error handling"""
    try:
        # Get Ivanti plugin
        kernel = self._build_kernel()
        kernel.add_plugin(IvantiPlugin(self.config.ivanti_api_url), plugin_name="ivanti")
        create_func = kernel.get_function("ivanti", "create_incident")
        
        # Invoke with explicit string parameters
        result = await create_func.invoke(
            kernel,
            subject=str(ticket.subject),
            symptom=str(ticket.description),
            impact=classification.priority,
            category=classification.category,
            service="General IT Support",
            owner_team=classification.team,
            status="Logged",
        )
        
        # Check if result indicates success
        if result and result.value and isinstance(result.value, dict):
            if result.value.get("success"):
                return {"status": "success", "error": None, "data": result.value}
            else:
                return {"status": "failed", "error": result.value.get("error", "Unknown error"), "data": None}
        
        return {"status": "success", "error": None, "data": result.value if result else None}
    
    except Exception as e:
        logger.error(f"Ivanti incident creation failed: {e}")
        return {"status": "failed", "error": str(e), "data": None}


async def _safe_create_callback(
    self, ticket: TicketRequest, classification: ClassificationResult, conversation_id: str
) -> dict:
    """Safely create NICE callback with error handling"""
    try:
        # Get NICE plugin
        kernel = self._build_kernel()
        kernel.add_plugin(NICEPlugin(self.config.nice_api_url), plugin_name="nice")
        create_func = kernel.get_function("nice", "create_callback")
        
        # Invoke with explicit string parameters
        result = await create_func.invoke(
            kernel,
            skillId="12345",  # TODO: Get from config
            phoneNumber=str(ticket.phone_number),
            emailFrom=str(ticket.user_email),
            firstName=str(ticket.user_first_name or ""),
            lastName=str(ticket.user_last_name or ""),
            notes=f"{ticket.subject}. {ticket.description}",
            priority=5,  # Default
            mediaType=4,  # Phone call
        )
        
        # Check if result indicates success
        if result and result.value and isinstance(result.value, dict):
            if result.value.get("success"):
                return {"status": "success", "error": None, "data": result.value}
            else:
                return {"status": "failed", "error": result.value.get("error", "Unknown error"), "data": None}
        
        return {"status": "success", "error": None, "data": result.value if result else None}
    
    except Exception as e:
        logger.error(f"NICE callback creation failed: {e}")
        return {"status": "failed", "error": str(e), "data": None}
