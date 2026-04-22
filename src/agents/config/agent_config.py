"""
Agent Configuration
Centralized configuration for knowledge-based agents and API endpoints
"""

import os
from typing import Optional
from dataclasses import dataclass


@dataclass
class AgentConfig:
    """Configuration for knowledge-based agents and API services"""
    
    # Azure OpenAI (Foundry model endpoint) - REQUIRED
    azure_openai_endpoint: str
    azure_openai_deployment: str
    azure_openai_api_version: str
    azure_openai_embedding_deployment: str
    azure_openai_api_key: str
    
    # Azure AI Search - REQUIRED
    azure_search_endpoint: str
    azure_search_index: str
    azure_search_key: str
    kb_top_k: int
    kb_content_field: str
    kb_semantic_config: str

    # Azure Computer Vision (vectorizeText / vectorizeImage) - REQUIRED
    azure_vision_endpoint: str
    azure_vision_key: str
    
    # Backend API Service URLs (FastAPI services) - REQUIRED
    ivanti_api_url: str
    nice_api_url: str
    
    # Cosmos DB (chat history) - REQUIRED
    cosmos_endpoint: str
    cosmos_key: str
    cosmos_database: str
    cosmos_container: str
    
    # Azure Resources - OPTIONAL (with defaults)
    subscription_id: Optional[str] = None
    resource_group: Optional[str] = None
    location: Optional[str] = None
    
    # Monitoring - OPTIONAL (with defaults)
    app_insights_connection_string: Optional[str] = None
    log_level: str = "INFO"
    
    def __init__(self):
        """Load configuration from environment variables"""
        # Azure OpenAI (Foundry) configuration
        self.azure_openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
        self.azure_openai_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
        self.azure_openai_api_version = os.getenv("AZURE_OPENAI_API_VERSION", "")
        self.azure_openai_embedding_deployment = os.getenv(
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", ""
        )
        self.azure_openai_api_key = os.getenv("AZURE_OPENAI_API_KEY", "")
        
        # Azure AI Search configuration
        self.azure_search_endpoint = os.getenv("AZURE_SEARCH_ENDPOINT", "")
        self.azure_search_index = os.getenv("AZURE_SEARCH_INDEX", "")
        self.azure_search_key = os.getenv("AZURE_SEARCH_KEY", "")
        self.kb_top_k = int(os.getenv("KB_TOP_K", "5"))
        self.kb_content_field = os.getenv("KB_CONTENT_FIELD", "content")
        self.kb_semantic_config = os.getenv("KB_SEMANTIC_CONFIG", "")

        # Azure Computer Vision (multimodal embeddings)
        self.azure_vision_endpoint = os.getenv("AZURE_VISION_ENDPOINT", "")
        self.azure_vision_key = os.getenv("AZURE_VISION_KEY", "")

        # Backend API URLs (FastAPI services)
        self.ivanti_api_url = os.getenv("IVANTI_API_URL", "http://ivanti-api:8000")
        self.nice_api_url = os.getenv("NICE_API_URL", "http://nice-api:8001")
        
        # Azure resources
        self.subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID")
        self.resource_group = os.getenv("RESOURCE_GROUP")
        self.location = os.getenv("LOCATION", "usgovvirginia")

        # Cosmos DB
        self.cosmos_endpoint = os.getenv("COSMOSDB_ENDPOINT", "")
        self.cosmos_key = os.getenv("COSMOSDB_KEY", "")
        self.cosmos_database = os.getenv("COSMOSDB_DATABASE", "itsm-chat")
        self.cosmos_container = os.getenv("COSMOSDB_CONTAINER", "history")
        
        # Monitoring
        self.app_insights_connection_string = os.getenv(
            "APPLICATIONINSIGHTS_CONNECTION_STRING"
        )
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
    
    def validate(self) -> bool:
        """Validate required configuration"""
        required = [
            ("AZURE_OPENAI_ENDPOINT", self.azure_openai_endpoint),
            ("AZURE_OPENAI_DEPLOYMENT", self.azure_openai_deployment),
            ("AZURE_OPENAI_API_VERSION", self.azure_openai_api_version),
            ("AZURE_OPENAI_API_KEY", self.azure_openai_api_key),
            ("AZURE_SEARCH_ENDPOINT", self.azure_search_endpoint),
            ("AZURE_SEARCH_INDEX", self.azure_search_index),
            ("AZURE_SEARCH_KEY", self.azure_search_key),
            ("KB_CONTENT_FIELD", self.kb_content_field),
            ("AZURE_VISION_ENDPOINT", self.azure_vision_endpoint),
            ("AZURE_VISION_KEY", self.azure_vision_key),
            ("COSMOSDB_ENDPOINT", self.cosmos_endpoint),
            ("COSMOSDB_KEY", self.cosmos_key),
        ]
        
        missing = []
        for name, value in required:
            if not value or value.startswith("your-") or value == "":
                missing.append(name)
        
        if missing:
            raise ValueError(
                f"Missing or invalid required configuration: {', '.join(missing)}\n"
                f"Please update your .env file with valid values."
            )
        
        return True
    
    def __str__(self) -> str:
        """String representation (safe - no sensitive data)"""
        return f"""AgentConfig:
  Azure OpenAI Endpoint: {self.azure_openai_endpoint[:50]}...
  Deployment: {self.azure_openai_deployment}
  API Version: {self.azure_openai_api_version}
  Embedding Deployment: {self.azure_openai_embedding_deployment}
  Search Endpoint: {self.azure_search_endpoint[:50]}...
  Search Index: {self.azure_search_index}
  KB Top K: {self.kb_top_k}
  KB Content Field: {self.kb_content_field}
  KB Semantic Config: {self.kb_semantic_config}
  Vision Endpoint: {self.azure_vision_endpoint[:50]}...
  Ivanti API: {self.ivanti_api_url}
  NICE API: {self.nice_api_url}
  Cosmos Endpoint: {self.cosmos_endpoint[:50]}...
  Cosmos Database: {self.cosmos_database}
  Cosmos Container: {self.cosmos_container}
  Log Level: {self.log_level}
"""
