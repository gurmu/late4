"""
Microsoft Teams Bot for ITSM Multi-Agent Assistant

Interfaces with the hybrid MultiAgentOrchestrator.  Supports multi-turn
conversations where final=false means the bot is waiting for the user
to reply (e.g., "Reply with 1 or 2").  Conversation state is tracked
in Cosmos DB + in-memory cache so it survives across Teams activities.

Supports image attachments: when a user attaches a screenshot or image,
the bot downloads it and passes the raw bytes to the orchestrator for
Azure Vision vectorizeImage embedding and multimodal KB search.
"""

import aiohttp
from botbuilder.core import ActivityHandler, TurnContext, MessageFactory
from botbuilder.schema import Activity, ActivityTypes, ChannelAccount
from agents.multi_agent_orchestrator import MultiAgentOrchestrator
import logging

logger = logging.getLogger(__name__)

# Image MIME types we can process via Azure Vision vectorizeImage
IMAGE_MIME_TYPES = {
    "image/png", "image/jpeg", "image/jpg",
    "image/gif", "image/bmp", "image/webp",
}


class ITSMTeamsBot(ActivityHandler):
    """Teams bot -- delegates to the hybrid orchestrator on every turn."""

    def __init__(self):
        self.orchestrator = MultiAgentOrchestrator()
        logger.info("ITSM Teams Bot initialized (hybrid orchestrator)")

    async def _download_image_attachment(
        self, turn_context: TurnContext
    ) -> bytes | None:
        """
        Download the first image attachment from a Teams message.

        Teams provides a content_url for each attachment. For images,
        we download the raw bytes so the orchestrator can pass them to
        Azure Vision vectorizeImage for 1024D embedding.

        Returns raw image bytes, or None if no image attachment found.
        """
        if not turn_context.activity.attachments:
            return None

        for attachment in turn_context.activity.attachments:
            content_type = (attachment.content_type or "").lower()

            if content_type not in IMAGE_MIME_TYPES:
                continue

            download_url = attachment.content_url
            if not download_url:
                logger.warning(
                    f"Image attachment '{attachment.name}' has no content_url"
                )
                continue

            try:
                # Build auth headers for downloading from Teams service
                headers = {}
                connector_client = turn_context.turn_state.get(
                    "ConnectorClient"
                )
                if connector_client:
                    # Try to get auth token for the download URL
                    try:
                        creds = getattr(connector_client, "config", None)
                        if creds and hasattr(creds, "credentials"):
                            token = await creds.credentials.get_token(
                                "https://api.botframework.com/.default"
                            )
                            if token:
                                headers["Authorization"] = f"Bearer {token.token}"
                    except Exception as auth_err:
                        logger.debug(
                            f"Could not get auth token for attachment download "
                            f"(will try without): {auth_err}"
                        )

                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        download_url,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as resp:
                        if resp.status == 200:
                            image_bytes = await resp.read()
                            logger.info(
                                f"Downloaded image: {attachment.name}, "
                                f"size={len(image_bytes)} bytes, "
                                f"type={content_type}"
                            )
                            return image_bytes
                        else:
                            logger.error(
                                f"Failed to download image '{attachment.name}': "
                                f"HTTP {resp.status}"
                            )
            except Exception as e:
                logger.error(f"Error downloading image attachment: {e}")

        return None

    async def on_message_activity(self, turn_context: TurnContext):
        """Handle incoming messages from Teams."""
        try:
            conversation_id = turn_context.activity.conversation.id

            # Build user message text
            user_message = turn_context.activity.text or ""
            image_bytes = None

            if turn_context.activity.attachments:
                # Try to download image attachments for visual search
                image_bytes = await self._download_image_attachment(turn_context)

                # List non-image attachment names (still "not analyzed")
                non_image_names = [
                    a.name
                    for a in turn_context.activity.attachments
                    if a.name
                    and (a.content_type or "").lower() not in IMAGE_MIME_TYPES
                ]
                if non_image_names:
                    user_message += (
                        f"\n\nUser attached files: {', '.join(non_image_names)}."
                        " Attachments are not analyzed yet."
                    )

                if image_bytes:
                    user_message += (
                        "\n\n[User attached an image for visual search]"
                    )

            if not user_message.strip() and not image_bytes:
                await turn_context.send_activity(
                    MessageFactory.text(
                        "Please enter a message so I can help you."
                    )
                )
                return

            logger.info(
                f"Message from conv={conversation_id}: {user_message[:80]}..."
                f"{' [+image]' if image_bytes else ''}"
            )

            # Show typing indicator while processing
            await turn_context.send_activity(
                Activity(type=ActivityTypes.typing)
            )

            # Orchestrator handles KB search, LLM reasoning, invariant
            # enforcement, and multi-turn state -- all in one call.
            response = await self.orchestrator.run_conversation(
                user_message, conversation_id, image_bytes=image_bytes
            )

            # Send plain-text response to Teams
            await turn_context.send_activity(MessageFactory.text(response))
            logger.info("Response sent to Teams")

        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            await turn_context.send_activity(
                MessageFactory.text(
                    "Sorry, I encountered an error processing your request. "
                    "Please try again or contact the help desk directly."
                )
            )

    async def on_members_added_activity(
        self, members_added: list[ChannelAccount], turn_context: TurnContext
    ):
        """Handle when bot is added to a conversation."""
        for member in members_added:
            if member.id != turn_context.activity.recipient.id:
                welcome = (
                    "Hello! I'm your ITSM Assistant. I can help with:\n\n"
                    "- IT support issues (VPN, login, network, software)\n"
                    "- Searching the ITSM Knowledge Base for solutions\n"
                    "- Creating incidents or callback requests\n"
                    "- Analyzing screenshots for troubleshooting\n\n"
                    "How can I help you today?"
                )
                await turn_context.send_activity(MessageFactory.text(welcome))
                logger.info("Welcome message sent")
