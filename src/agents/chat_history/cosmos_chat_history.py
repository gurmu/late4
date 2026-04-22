"""
Cosmos DB chat history for Semantic Kernel agents.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from azure.cosmos import CosmosClient, PartitionKey
from semantic_kernel.contents import ChatHistory

logger = logging.getLogger(__name__)


class CosmosDBChatHistory:
    """Persist chat messages to Cosmos DB and rebuild ChatHistory."""

    def __init__(
        self,
        endpoint: str,
        key: str,
        database_name: str,
        container_name: str,
    ):
        self._client = CosmosClient(endpoint, credential=key)
        self._db = self._client.create_database_if_not_exists(id=database_name)
        self._container = self._db.create_container_if_not_exists(
            id=container_name,
            partition_key=PartitionKey(path="/conversation_id"),
        )

    def load(self, conversation_id: str) -> ChatHistory:
        history = ChatHistory()
        query = "SELECT * FROM c WHERE c.conversation_id = @cid ORDER BY c.timestamp"
        params = [{"name": "@cid", "value": conversation_id}]
        items = list(self._container.query_items(query=query, parameters=params, enable_cross_partition_query=True))
        for item in items:
            role = item.get("role")
            content = item.get("content")
            if role == "user":
                history.add_user_message(content)
            elif role == "assistant":
                history.add_assistant_message(content)
            else:
                history.add_system_message(content)
        return history

    def append(self, conversation_id: str, role: str, content: str) -> None:
        item = {
            "id": f"{conversation_id}:{int(time.time() * 1000)}",
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "timestamp": time.time(),
        }
        self._container.create_item(body=item)

    def append_history(self, conversation_id: str, history: ChatHistory) -> None:
        for message in history.messages:
            role = getattr(message, "role", "assistant")
            role_value = role.value if hasattr(role, "value") else str(role)
            role_value = role_value.lower()
            if "user" in role_value:
                role_value = "user"
            elif "system" in role_value:
                role_value = "system"
            else:
                role_value = "assistant"
            self.append(conversation_id, role_value, message.content)
