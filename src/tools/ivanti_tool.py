"""
Ivanti Function Tool
Wraps the Ivanti FastAPI service as an Azure AI Agent function tool
"""

import httpx
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def create_ivanti_tool_definition() -> Dict[str, Any]:
    """
    Create the function tool definition for Ivanti incident creation
    This is what the agent sees as an available tool
    """
    return {
        "type": "function",
        "function": {
            "name": "create_ivanti_incident",
            "description": """Creates an incident ticket in the Ivanti ITSM system.
            
            Use this tool to create a formal incident record after analyzing the ticket with knowledge bases.
            
            Required fields:
            - subject: Brief title of the incident
            - symptom: Detailed description of the issue
            - impact: Business impact level (Low/Medium/High/Critical)
            - category: Issue category (Hardware/Software/Network/Other)
            - service: Related service (Software/Hardware/Network/Support)
            - owner_team: Team assigned to handle the incident
            
            Returns incident ID and number for tracking.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {
                        "type": "string",
                        "description": "Incident subject/title (1-255 characters)"
                    },
                    "symptom": {
                        "type": "string",
                        "description": "Detailed symptom description"
                    },
                    "status": {
                        "type": "string",
                        "enum": ["Logged", "Active", "Waiting", "Resolved", "Closed"],
                        "description": "Incident status",
                        "default": "Logged"
                    },
                    "impact": {
                        "type": "string",
                        "enum": ["Low", "Medium", "High", "Critical"],
                        "description": "Business impact level"
                    },
                    "category": {
                        "type": "string",
                        "enum": ["Hardware", "Software", "Network", "Other"],
                        "description": "Issue category"
                    },
                    "service": {
                        "type": "string",
                        "enum": ["Software", "Hardware", "Network", "Support"],
                        "description": "Related service"
                    },
                    "owner_team": {
                        "type": "string",
                        "description": "Team assigned to handle this incident"
                    }
                },
                "required": ["subject", "symptom", "impact", "category", "service", "owner_team"]
            }
        }
    }


class IvantiTool:
    """
    Function tool implementation for Ivanti API
    Handles actual HTTP calls to the FastAPI service
    """
    
    def __init__(self, api_url: str, timeout: int = 30):
        """
        Initialize Ivanti tool
        
        Args:
            api_url: Base URL of Ivanti API (e.g., http://localhost:8000)
            timeout: Request timeout in seconds
        """
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)
        
        logger.info(f"Ivanti tool initialized: {self.api_url}")
    
    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the Ivanti incident creation
        
        Args:
            arguments: Function arguments from the agent
            
        Returns:
            Response from Ivanti API
        """
        logger.info(f"Creating Ivanti incident: {arguments.get('subject')}")
        
        try:
            # Prepare request payload matching FastAPI schema
            payload = {
                "subject": arguments["subject"],
                "symptom": arguments["symptom"],
                "status": arguments.get("status", "Logged"),
                "impact": arguments["impact"],
                "category": arguments["category"],
                "service": arguments["service"],
                "owner_team": arguments["owner_team"]
            }
            
            # Call Ivanti API
            url = f"{self.api_url}/incidents"
            logger.debug(f"POST {url}")
            logger.debug(f"Payload: {payload}")
            
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            
            result = response.json()
            
            logger.info(f"✓ Incident created successfully")
            logger.info(f"  Incident ID: {result.get('incident_id')}")
            logger.info(f"  Incident Number: {result.get('data', {}).get('IncidentNumber')}")
            
            return {
                "success": True,
                "incident_id": result.get("incident_id"),
                "incident_number": result.get("data", {}).get("IncidentNumber"),
                "message": result.get("message"),
                "full_response": result
            }
            
        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP error {e.response.status_code}: {e.response.text}"
            logger.error(f"✗ {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "status_code": e.response.status_code
            }
            
        except httpx.RequestError as e:
            error_msg = f"Request error: {str(e)}"
            logger.error(f"✗ {error_msg}")
            return {
                "success": False,
                "error": error_msg
            }
            
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(f"✗ {error_msg}")
            return {
                "success": False,
                "error": error_msg
            }
    
    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()
    
    def __del__(self):
        """Cleanup on deletion"""
        try:
            import asyncio
            asyncio.run(self.close())
        except:
            pass


# Standalone test function
async def test_ivanti_tool():
    """Test the Ivanti tool directly"""
    tool = IvantiTool("http://localhost:8000")
    
    test_args = {
        "subject": "Test Incident",
        "symptom": "This is a test incident created by the tool",
        "impact": "Low",
        "category": "Software",
        "service": "Software",
        "owner_team": "IT Support"
    }
    
    result = await tool.execute(test_args)
    print("Result:", result)
    
    await tool.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_ivanti_tool())