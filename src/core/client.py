"""
API Client for external services
Async HTTP client for calling FastAPI backend services
"""

import httpx
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class APIClient:
    """Generic async HTTP client for API services"""
    
    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)
    
    async def get(self, endpoint: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Make GET request"""
        url = f"{self.base_url}{endpoint}"
        logger.debug(f"GET {url}")
        
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()
    
    async def post(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Make POST request"""
        url = f"{self.base_url}{endpoint}"
        logger.debug(f"POST {url}")
        
        response = await self.client.post(url, json=data)
        response.raise_for_status()
        return response.json()
    
    async def delete(self, endpoint: str) -> Dict[str, Any]:
        """Make DELETE request"""
        url = f"{self.base_url}{endpoint}"
        logger.debug(f"DELETE {url}")
        
        response = await self.client.delete(url)
        response.raise_for_status()
        return response.json()
    
    async def close(self):
        """Close client connection"""
        await self.client.aclose()
    
    def __del__(self):
        """Cleanup on deletion"""
        try:
            import asyncio
            asyncio.run(self.close())
        except:
            pass