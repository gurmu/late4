# Secrets Template - Azure GCC

This document lists required configuration values for the ITSM GCC assistant.
Never commit real secrets to source control.

## Required Configuration

### Azure OpenAI (Foundry)
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_DEPLOYMENT`
- `AZURE_OPENAI_API_VERSION`
- `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`

### Azure AI Search
- `AZURE_SEARCH_ENDPOINT`
- `AZURE_SEARCH_INDEX`
- `KB_CONTENT_FIELD`
- `KB_SEMANTIC_CONFIG`

### Azure Identity (GCC)
- `AZURE_AUTHORITY_HOST` = `https://login.microsoftonline.us`

### Microsoft Teams Bot
- `MICROSOFT_APP_ID`
- `MICROSOFT_APP_PASSWORD`
- `BOT_FRAMEWORK_CHANNEL_SERVICE` = `https://botframework.azure.us`
- `BOT_FRAMEWORK_OAUTH_URL` = `https://login.microsoftonline.us/botframework/v1/.well-known/openidconfiguration`

### Optional (Deployment)
- `ACR_NAME`
- `RESOURCE_GROUP`
- `LOCATION`

## Ivanti / NICE

These services are accessed through the local API layers:
- `IVANTI_API_URL`
- `NICE_API_URL`

If those APIs require their own secrets, store them in your corporate secrets manager.
