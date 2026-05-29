"""
Run this script from the project root to write the correct src/teams_server.py.
Usage:  python fix_teams_server.py
"""
import os, ast

CONTENT = '''\
"""
Web server for Microsoft Teams Bot (Azure Government / GCC)
"""

from aiohttp import web
from aiohttp.web import Request, Response
from botbuilder.integration.aiohttp import CloudAdapter, ConfigurationBotFrameworkAuthentication
from botbuilder.schema import Activity
from teams_bot import ITSMTeamsBot
import os
import sys
from dotenv import load_dotenv
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format=\'%(asctime)s - %(name)s - %(levelname)s - %(message)s\'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Bot Framework settings
APP_ID = os.getenv("MICROSOFT_APP_ID")
APP_PASSWORD = os.getenv("MICROSOFT_APP_PASSWORD")
BOT_TYPE = os.getenv("BOT_TYPE", "").strip()
APP_MSI_RESOURCE_ID = os.getenv("APP_MSI_RESOURCE_ID")
APP_TENANT_ID = os.getenv("APP_TENANT_ID", "").strip()
PORT = int(os.getenv("PORT", "3978"))

using_managed_identity = BOT_TYPE.lower() in {
    "user-assigned managed identity",
    "userassignedmanagedidentity",
    "user-assigned",
    "managedidentity",
    "managed-identity",
}

if not APP_ID:
    logger.error("MICROSOFT_APP_ID must be set in .env file")
    print("\\nERROR: Missing Teams bot credentials!")
    print("Please add to your .env file:")
    print("MICROSOFT_APP_ID=your-app-id")
    if not using_managed_identity:
        print("MICROSOFT_APP_PASSWORD=your-app-secret")
    print("\\nSee TEAMS_DEPLOYMENT.md for instructions on getting these credentials.")
    sys.exit(1)

logger.info("Bot App ID loaded from environment.")

if using_managed_identity:
    logger.info("Bot type: User-Assigned Managed Identity (no app password expected).")
    if APP_MSI_RESOURCE_ID:
        logger.info("App MSI Resource ID configured.")
else:
    if not APP_PASSWORD:
        logger.error("MICROSOFT_APP_PASSWORD must be set for non-managed identity bots.")
        print("\\nERROR: Missing Teams bot secret!")
        print("Please add to your .env file:")
        print("MICROSOFT_APP_PASSWORD=your-app-secret")
        sys.exit(1)

if not APP_TENANT_ID:
    logger.warning(
        "APP_TENANT_ID not set. Single Tenant GCC bots must set this "
        "to the Azure AD tenant ID shown in Azure Bot Configuration."
    )
else:
    logger.info("Bot tenant ID: %s", APP_TENANT_ID)


# ---------------------------------------------------------------------------
# GCC (Azure Government / Single Tenant) authentication configuration.
#
# ConfigurationBotFrameworkAuthentication reads a plain config object whose
# attributes tell the SDK which GCC endpoints to use for:
#   - Outbound bot credentials  (TO_CHANNEL_FROM_BOT_*)
#   - Inbound token validation  (TO_BOT_FROM_CHANNEL_*)
#
# Critical for Single Tenant GCC:
#   TO_BOT_FROM_CHANNEL_TOKEN_ISSUER must match the actual "iss" claim in the
#   JWT that Teams sends.  For Single Tenant GCC (msaAppType = SingleTenant)
#   Teams signs tokens with  https://sts.windows.net/{tenant-id}/
#   NOT with  https://api.botframework.us  (that is the multi-tenant issuer).
# ---------------------------------------------------------------------------
class _GCCConfig:
    APP_ID = APP_ID
    APP_PASSWORD = APP_PASSWORD
    APP_TYPE = "SingleTenant"
    APP_TENANTID = APP_TENANT_ID

    # Inbound: which OpenID metadata URL to fetch signing keys from
    TO_BOT_FROM_CHANNEL_OPENID_METADATA_URL = (
        "https://login.botframework.azure.us/v1/.well-known/openidconfiguration"
    )

    # Inbound: expected token issuer from Teams Government (Single Tenant)
    TO_BOT_FROM_CHANNEL_TOKEN_ISSUER = (
        "https://sts.windows.net/" + (APP_TENANT_ID or "") + "/"
    )

    # Inbound: emulator OpenID metadata (GCC emulator endpoint)
    TO_BOT_FROM_EMULATOR_OPENID_METADATA_URL = (
        "https://login.microsoftonline.us/"
        "cab8a31a-1906-4287-a0d8-4eef66b95f6e/v2.0/.well-known/openid-configuration"
    )

    # Outbound: login URL for bot-to-channel auth (Azure Government).
    # SingleTenant GCC: the bot\'s App Registration lives in the customer\'s
    # government tenant (APP_TENANT_ID), NOT in Microsoft\'s shared Bot Framework
    # tenant (MicrosoftServices.onmicrosoft.us).  Using the wrong tenant here
    # causes the connector client to get a token that the GCC serviceUrl rejects
    # with 401 Unauthorized.  Fall back to the shared tenant only if no tenant
    # ID is configured (pure multi-tenant bots).
    TO_CHANNEL_FROM_BOT_LOGIN_URL = (
        "https://login.microsoftonline.us/"
        + (APP_TENANT_ID or "MicrosoftServices.onmicrosoft.us")
    )

    # Outbound: OAuth scope for bot-to-channel auth
    TO_CHANNEL_FROM_BOT_OAUTH_SCOPE = "https://api.botframework.azure.us"

    # Channel service flag -- signals GCC to the SDK
    CHANNEL_SERVICE = "https://botframework.azure.us"

    # OAuth endpoint for OAuthCard / sign-in flows
    OAUTH_URL = "https://tokengcch.botframework.azure.us/"

    VALIDATE_AUTHORITY = True


BOT_AUTH = ConfigurationBotFrameworkAuthentication(_GCCConfig)
ADAPTER = CloudAdapter(BOT_AUTH)

logger.info("CloudAdapter initialised with GCC configuration.")
logger.info(
    "Token issuer expected: %s",
    _GCCConfig.TO_BOT_FROM_CHANNEL_TOKEN_ISSUER,
)
logger.info(
    "Outbound login URL  : %s",
    _GCCConfig.TO_CHANNEL_FROM_BOT_LOGIN_URL,
)


# Error handler
async def on_error(context, error):
    logger.error("Bot error: %s", error, exc_info=True)
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

        # CloudAdapter: auth_header comes FIRST, then activity
        response = await ADAPTER.process_activity(auth_header, activity, BOT.on_turn)

        if response:
            return Response(status=response.status, text=response.body)
        return Response(status=201)

    except Exception as exception:
        logger.error("Error processing request: %s", exception, exc_info=True)
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
        logger.info("Starting ITSM Teams Bot Server (GCC)")
        logger.info("=" * 70)
        logger.info("Port: %s", PORT)
        logger.info("Endpoint: http://0.0.0.0:%s/api/messages", PORT)
        logger.info("=" * 70)

        web.run_app(APP, host="0.0.0.0", port=PORT)

    except Exception as error:
        logger.error("Failed to start server: %s", error, exc_info=True)
        raise
'''

out = os.path.join("src", "teams_server.py")
os.makedirs("src", exist_ok=True)
with open(out, "w", encoding="utf-8") as fh:
    fh.write(CONTENT)
print("Written:", os.path.abspath(out))

# Syntax check
try:
    ast.parse(CONTENT)
    print("Syntax OK")
except SyntaxError as e:
    print("SYNTAX ERROR:", e)

python fix_teams_server.py