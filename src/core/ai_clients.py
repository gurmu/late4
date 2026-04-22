"""
Azure AI clients for GCC: Azure OpenAI + Azure AI Search

DEPRECATED: This module is not used by the active multi-agent orchestrator.
The active search pipeline uses src/agents/plugins/itsm_search_plugin.py
with Azure Vision embeddings (VISION_embedding field in itsm-indexv2).
This file is retained for reference only.
"""

import logging
from typing import Any

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from openai import AzureOpenAI

logger = logging.getLogger(__name__)


class AIClients:
    """Holds Azure OpenAI and Azure AI Search clients"""

    def __init__(self, config: Any):
        credential = DefaultAzureCredential()

        self.search_client = SearchClient(
            endpoint=config.azure_search_endpoint,
            index_name=config.azure_search_index,
            credential=credential,
        )

        token_provider = get_bearer_token_provider(
            credential, "https://cognitiveservices.azure.com/.default"
        )
        self.openai_client = AzureOpenAI(
            azure_endpoint=config.azure_openai_endpoint,
            api_version=config.azure_openai_api_version,
            azure_ad_token_provider=token_provider,
        )
        self.deployment = config.azure_openai_deployment
        self.embedding_deployment = config.azure_openai_embedding_deployment

    def _extract_content(self, doc: dict, content_field: str) -> str:
        if content_field:
            value = doc.get(content_field)
            if isinstance(value, str) and value.strip():
                return value.strip()

        for key in ["content", "text", "chunk", "chunk_text", "body"]:
            value = doc.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        parts = []
        for key, value in doc.items():
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
        return "\n".join(parts).strip()

    def _embed_text(self, text: str) -> list[float]:
        if not self.embedding_deployment:
            return []
        response = self.openai_client.embeddings.create(
            model=self.embedding_deployment,
            input=text,
        )
        return response.data[0].embedding

    def search_kb(
        self,
        query: str,
        top_k: int,
        content_field: str,
        semantic_config: str,
    ) -> list[dict]:
        if top_k <= 0:
            return []

        search_kwargs = {"search_text": query, "top": top_k}
        if semantic_config:
            search_kwargs["query_type"] = "semantic"
            search_kwargs["semantic_configuration_name"] = semantic_config

        if self.embedding_deployment:
            vector = self._embed_text(query)
            if vector:
                search_kwargs["vector_queries"] = [
                    VectorizedQuery(
                        vector=vector,
                        fields="text_embedding",
                        k_nearest_neighbors=top_k,
                    )
                ]

        results = self.search_client.search(**search_kwargs)
        snippets = []
        for result in results:
            doc = dict(result)
            content = self._extract_content(doc, content_field)
            if content:
                snippets.append({
                    "content": content,
                    "file_name": doc.get("file_name"),
                    "page_num": doc.get("page_num"),
                    "image_url": doc.get("image_url"),
                    "doc": doc
                })

        logger.info("KB snippets retrieved: %s", len(snippets))
        return snippets

    def chat(self, messages: list[dict]) -> str:
        response = self.openai_client.chat.completions.create(
            model=self.deployment,
            messages=messages,
            temperature=0.2,
        )
        return response.choices[0].message.content or ""
