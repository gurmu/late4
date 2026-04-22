"""
ITSM Search Plugin with Azure Vision Multimodal Embeddings

Uses Azure Computer Vision (Florence model) for unified 1024-dim embeddings:
- vectorizeText: text query → 1024D vector
- vectorizeImage: image bytes → 1024D vector (same embedding space)
- Single vector field: VISION_embedding in Azure AI Search (itsm-indexv2)

Both text and image embeddings live in the SAME vector space, enabling:
- Text query → matches text chunks AND images
- Image query → matches images AND related text chunks

Returns STRUCTURED JSON (not string headers):
  {
    "kb_hits_count": <int>,
    "results": [
      {"title": ..., "content": ..., "source": ..., "score": ..., "image_url": ..., "pdf_url": ...}
    ]
  }
Score fields are included for observability/logging but are NOT used
for routing decisions.  The LLM (not a threshold) decides whether
the results are relevant enough to answer the user's question.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import requests
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from semantic_kernel.functions import kernel_function

logger = logging.getLogger(__name__)

# Azure Vision API configuration
_VISION_API_VERSION = "2024-02-01"
_VISION_MODEL_VERSION = "2023-04-15"  # Multi-lingual Florence model
_VISION_RETRY_MAX = 3
_VISION_RETRY_BACKOFF = 2.0  # seconds
_VISION_EMBEDDING_DIM = 1024


class ITSMSearchPlugin:
    """Semantic Kernel plugin for Azure AI Search with Azure Vision embeddings."""

    def __init__(
        self,
        endpoint: str,
        index_name: str,
        api_key: str,
        content_field: str = "content",
        vision_endpoint: str = "",
        vision_key: str = "",
    ):
        self._content_field = content_field
        self._client = SearchClient(
            endpoint=endpoint,
            index_name=index_name,
            credential=AzureKeyCredential(api_key),
        )

        # Azure Vision (Florence model) for 1024D embeddings
        self._vision_endpoint = vision_endpoint.rstrip("/") if vision_endpoint else ""
        self._vision_key = vision_key

        # Image bytes for the current search (set by orchestrator before search,
        # consumed and cleared during search). This avoids changing the
        # kernel_function signature which is called by the LLM via tool calling.
        self._pending_image_bytes: bytes | None = None

    # ------------------------------------------------------------------
    # Azure Vision embedding methods
    # ------------------------------------------------------------------
    def _get_vision_text_embedding(self, text: str) -> list[float] | None:
        """
        Call Azure Vision vectorizeText API → 1024D embedding.

        Azure Vision accepts 1-70 words. Longer text is truncated.
        Returns None on failure (caller decides how to handle).
        """
        if not self._vision_endpoint or not self._vision_key:
            logger.warning("Azure Vision not configured; skipping text embedding")
            return None

        if not text or not text.strip():
            return None

        # Azure Vision text limit: 70 words max
        words = text.strip().split()
        if len(words) > 70:
            text_truncated = " ".join(words[:70])
        else:
            text_truncated = text.strip()

        url = (
            f"{self._vision_endpoint}/computervision/retrieval:vectorizeText"
            f"?api-version={_VISION_API_VERSION}"
            f"&model-version={_VISION_MODEL_VERSION}"
        )
        headers = {
            "Content-Type": "application/json",
            "Ocp-Apim-Subscription-Key": self._vision_key,
        }
        body = {"text": text_truncated}

        for attempt in range(_VISION_RETRY_MAX):
            try:
                resp = requests.post(url, headers=headers, json=body, timeout=15)

                if resp.status_code == 200:
                    vector = resp.json().get("vector", [])
                    if len(vector) == _VISION_EMBEDDING_DIM:
                        logger.info("Vision text embedding: 1024D")
                        return vector
                    else:
                        logger.warning(
                            f"Unexpected vector dim: {len(vector)} (expected {_VISION_EMBEDDING_DIM})"
                        )
                        return vector if vector else None

                elif resp.status_code == 429:
                    retry_after = float(resp.headers.get("Retry-After", _VISION_RETRY_BACKOFF))
                    wait = max(retry_after, _VISION_RETRY_BACKOFF * (attempt + 1))
                    logger.warning(f"Vision text rate-limited (429). Retry {attempt + 1}/{_VISION_RETRY_MAX} in {wait:.1f}s")
                    time.sleep(wait)
                    continue

                else:
                    logger.error(f"Vision vectorizeText error {resp.status_code}: {resp.text[:300]}")
                    return None

            except requests.exceptions.RequestException as e:
                logger.error(f"Vision vectorizeText request failed (attempt {attempt + 1}): {e}")
                if attempt < _VISION_RETRY_MAX - 1:
                    time.sleep(_VISION_RETRY_BACKOFF)

        logger.error("Vision vectorizeText: max retries exhausted")
        return None

    def _get_vision_image_embedding(self, image_bytes: bytes) -> list[float] | None:
        """
        Call Azure Vision vectorizeImage API → 1024D embedding.

        Accepts raw image bytes (PNG, JPEG, BMP, GIF). Max 20 MB.
        Returns None on failure.
        """
        if not self._vision_endpoint or not self._vision_key:
            logger.warning("Azure Vision not configured; skipping image embedding")
            return None

        if not image_bytes or len(image_bytes) == 0:
            return None

        # Azure Vision limit: 20 MB max
        if len(image_bytes) > 20 * 1024 * 1024:
            logger.warning(f"Image too large ({len(image_bytes)} bytes, max 20MB). Skipping.")
            return None

        url = (
            f"{self._vision_endpoint}/computervision/retrieval:vectorizeImage"
            f"?api-version={_VISION_API_VERSION}"
            f"&model-version={_VISION_MODEL_VERSION}"
        )
        headers = {
            "Content-Type": "application/octet-stream",
            "Ocp-Apim-Subscription-Key": self._vision_key,
        }

        for attempt in range(_VISION_RETRY_MAX):
            try:
                resp = requests.post(url, headers=headers, data=image_bytes, timeout=30)

                if resp.status_code == 200:
                    vector = resp.json().get("vector", [])
                    if len(vector) == _VISION_EMBEDDING_DIM:
                        logger.info("Vision image embedding: 1024D")
                        return vector
                    else:
                        logger.warning(
                            f"Unexpected vector dim: {len(vector)} (expected {_VISION_EMBEDDING_DIM})"
                        )
                        return vector if vector else None

                elif resp.status_code == 429:
                    retry_after = float(resp.headers.get("Retry-After", _VISION_RETRY_BACKOFF))
                    wait = max(retry_after, _VISION_RETRY_BACKOFF * (attempt + 1))
                    logger.warning(f"Vision image rate-limited (429). Retry {attempt + 1}/{_VISION_RETRY_MAX} in {wait:.1f}s")
                    time.sleep(wait)
                    continue

                else:
                    logger.error(f"Vision vectorizeImage error {resp.status_code}: {resp.text[:300]}")
                    return None

            except requests.exceptions.RequestException as e:
                logger.error(f"Vision vectorizeImage request failed (attempt {attempt + 1}): {e}")
                if attempt < _VISION_RETRY_MAX - 1:
                    time.sleep(_VISION_RETRY_BACKOFF)

        logger.error("Vision vectorizeImage: max retries exhausted")
        return None

    # ------------------------------------------------------------------
    # Content extraction helper
    # ------------------------------------------------------------------
    def _extract_content(self, doc: dict[str, Any]) -> str:
        """Extract content from search result."""
        value = doc.get(self._content_field)
        if isinstance(value, str) and value.strip():
            return value.strip()
        for key in ["content", "text", "chunk", "chunk_text", "body"]:
            value = doc.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    # ------------------------------------------------------------------
    # Main search function (kernel_function for Semantic Kernel)
    # ------------------------------------------------------------------
    @kernel_function(
        name="search_kb",
        description="Search the ITSM knowledge base using Azure Vision vector hybrid search.",
    )
    def search_kb(
        self,
        query: str,
        top_k: int = 5,
        semantic_config: str | None = None,
        use_text_vectors: bool = True,
        use_image_vectors: bool = True,
    ) -> str:
        """
        Search with hybrid approach (keyword + Azure Vision vectors).

        Generates embeddings via Azure Vision REST API:
        - Text query → vectorizeText → 1024D → search VISION_embedding
        - Image bytes (if _pending_image_bytes set) → vectorizeImage → 1024D → search VISION_embedding

        When both text and image vectors are present, Azure AI Search
        uses Reciprocal Rank Fusion (RRF) to combine the results.

        Returns a JSON string with structured results:
        {
            "kb_hits_count": 3,
            "results": [
                {
                    "title": "file_name.pdf",
                    "content": "...",
                    "source": "file_name=x | page_num=5",
                    "score": 12.345,
                    "image_url": null,
                    "pdf_url": null
                },
                ...
            ]
        }

        If no results:  {"kb_hits_count": 0, "results": []}

        Scores are included for logging/observability only and are NOT
        used for routing decisions.
        """
        if not query.strip():
            return json.dumps({"kb_hits_count": 0, "results": [], "error": "No query provided."})

        # Base keyword search
        search_kwargs: dict[str, Any] = {
            "search_text": query,
            "top": top_k,
            "select": ["id", "file_name", "page_num", "content", "item_type", "image_url", "pdf_url"],
        }

        # Add semantic ranking if configured
        if semantic_config:
            search_kwargs["query_type"] = "semantic"
            search_kwargs["semantic_configuration_name"] = semantic_config
            logger.info(f"Using semantic search with config: {semantic_config}")

        # Build vector queries (unified 1024D VISION_embedding field)
        vector_queries = []

        # Text vector query
        if use_text_vectors and query.strip():
            text_vector = self._get_vision_text_embedding(query)
            if text_vector:
                vector_queries.append(
                    VectorizedQuery(
                        vector=text_vector,
                        fields="VISION_embedding",
                        k_nearest_neighbors=top_k,
                    )
                )
                logger.info("Added Vision text vector query (1024D → VISION_embedding)")

        # Image vector query (from pending attachment, if any)
        if use_image_vectors and self._pending_image_bytes:
            image_vector = self._get_vision_image_embedding(self._pending_image_bytes)
            if image_vector:
                vector_queries.append(
                    VectorizedQuery(
                        vector=image_vector,
                        fields="VISION_embedding",
                        k_nearest_neighbors=top_k,
                    )
                )
                logger.info("Added Vision image vector query (1024D → VISION_embedding)")
            # Clear after use — one-time consumption
            self._pending_image_bytes = None

        if vector_queries:
            search_kwargs["vector_queries"] = vector_queries

        # Execute search
        try:
            results = self._client.search(**search_kwargs)
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return json.dumps({"kb_hits_count": 0, "results": [], "error": str(e)})

        # Collect structured results
        result_items: list[dict[str, Any]] = []

        for result in results:
            doc = dict(result)
            content = self._extract_content(doc)
            if not content:
                continue

            # Capture the search score for logging (NOT for gating)
            score = doc.get("@search.score", 0.0)
            try:
                score = float(score)
            except (TypeError, ValueError):
                score = 0.0

            # Build source reference string
            source_parts = []
            if doc.get("file_name"):
                source_parts.append(f"file_name={doc['file_name']}")
            if doc.get("page_num") is not None:
                source_parts.append(f"page_num={doc['page_num']}")
            if doc.get("item_type"):
                source_parts.append(f"type={doc['item_type']}")

            result_items.append({
                "title": doc.get("file_name", "Unknown"),
                "content": content,
                "source": " | ".join(source_parts),
                "score": round(score, 4),
                "image_url": doc.get("image_url"),
                "pdf_url": doc.get("pdf_url"),
            })

        kb_hits_count = len(result_items)

        # Log scores for observability (NOT used for routing)
        if result_items:
            top_score = max(r["score"] for r in result_items)
            logger.info(
                f"KB search: hits={kb_hits_count}, top_score={top_score:.4f} "
                f"(logged for observability, NOT used for routing)"
            )
        else:
            logger.info("KB search: hits=0")

        output = {"kb_hits_count": kb_hits_count, "results": result_items}
        return json.dumps(output, ensure_ascii=False)
