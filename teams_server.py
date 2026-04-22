"""
Web server for Microsoft Teams Bot
"""

from aiohttp import web
from aiohttp.web import Request, Response
from botbuilder.core import BotFrameworkAdapterSettings, BotFrameworkAdapter
from botbuilder.schema import Activity
from teams_bot import ITSMTeamsBot
import os
import sys
from dotenv import load_dotenv
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Bot Framework settings
APP_ID = os.getenv("MICROSOFT_APP_ID")
APP_PASSWORD = os.getenv("MICROSOFT_APP_PASSWORD")
BOT_TYPE = os.getenv("BOT_TYPE", "").strip()
APP_MSI_RESOURCE_ID = os.getenv("APP_MSI_RESOURCE_ID")
CHANNEL_SERVICE = os.getenv("BOT_FRAMEWORK_CHANNEL_SERVICE")
OAUTH_URL = os.getenv("BOT_FRAMEWORK_OAUTH_URL")

using_managed_identity = BOT_TYPE.lower() in {
    "user-assigned managed identity",
    "userassignedmanagedidentity",
    "user-assigned",
    "managedidentity",
    "managed-identity",
}

if not APP_ID:
    logger.error("MICROSOFT_APP_ID must be set in .env file")
    print("\nERROR: Missing Teams bot credentials!")
    print("Please add to your .env file:")
    print("MICROSOFT_APP_ID=your-app-id")
    if not using_managed_identity:
        print("MICROSOFT_APP_PASSWORD=your-app-secret")
    print("\nSee TEAMS_DEPLOYMENT.md for instructions on getting these credentials.")
    sys.exit(1)

logger.info(f"Bot configured with App ID: {APP_ID[:8]}...")

if using_managed_identity:
    logger.info("Bot type: User-Assigned Managed Identity (no app password expected).")
    if APP_MSI_RESOURCE_ID:
        logger.info("App MSI Resource ID configured.")
else:
    if not APP_PASSWORD:
        logger.error("MICROSOFT_APP_PASSWORD must be set for non-managed identity bots.")
        print("\nERROR: Missing Teams bot secret!")
        print("Please add to your .env file:")
        print("MICROSOFT_APP_PASSWORD=your-app-secret")
        sys.exit(1)

SETTINGS = BotFrameworkAdapterSettings(APP_ID, APP_PASSWORD or None)
if CHANNEL_SERVICE:
    SETTINGS.channel_service = CHANNEL_SERVICE
else:
    logger.warning("BOT_FRAMEWORK_CHANNEL_SERVICE not set; GCC bots should use https://botframework.azure.us")
if OAUTH_URL:
    SETTINGS.oauth_endpoint = OAUTH_URL
else:
    logger.warning("BOT_FRAMEWORK_OAUTH_URL not set; GCC bots should use https://login.microsoftonline.us/botframework/v1/.well-known/openidconfiguration")
ADAPTER = BotFrameworkAdapter(SETTINGS)

# Error handler
async def on_error(context, error):
    logger.error(f"Bot error: {error}", exc_info=True)
    await context.send_activity("Sorry, something went wrong.")

ADAPTER.on_turn_error = on_error

# Create bot
BOT = ITSMTeamsBot()


async def messages(req: Request) -> Response:
    """Handle incoming messages from Teams"""
    logger.info("Received request to /api/messages")
    
    # Verify content type
    if "application/json" not in req.headers.get("Content-Type", ""):
        logger.error("Invalid content type")
        return Response(status=415, text="Content-Type must be application/json")

    try:
        # Parse request body
        body = await req.json()
        activity = Activity().deserialize(body)
        
        # Get auth header
        auth_header = req.headers.get("Authorization", "")
        
        # Process activity
        response = await ADAPTER.process_activity(activity, auth_header, BOT.on_turn)
        
        if response:
            return Response(status=response.status, text=response.body)
        return Response(status=201)
        
    except Exception as exception:
        logger.error(f"Error processing request: {exception}", exc_info=True)
        return Response(status=500, text=str(exception))


async def health_check(req: Request) -> Response:
    """Health check endpoint"""
    return Response(text="Bot is running", status=200)


# Create web app
APP = web.Application()
APP.router.add_post("/api/messages", messages)
APP.router.add_get("/health", health_check)
APP.router.add_get("/", health_check)


if __name__ == "__main__":
    try:
        logger.info("=" * 70)
        logger.info("Starting ITSM Teams Bot Server")
        logger.info("=" * 70)
        logger.info(f"App ID: {APP_ID[:8]}...")
        logger.info("Server will listen on: http://0.0.0.0:3978")
        logger.info("Endpoint: http://0.0.0.0:3978/api/messages")
        logger.info("=" * 70)
        
        web.run_app(APP, host="0.0.0.0", port=3978)
        
    except Exception as error:
        logger.error(f"Failed to start server: {error}", exc_info=True)
        raise
