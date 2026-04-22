# Azure GCC App Service Deployment Guide (Multi-Container)

This guide deploys the ITSM solution to Azure GCC using App Service (Linux)
with a multi-container docker-compose.yml. App Service is required for Teams
because it provides HTTPS endpoints.

## Prerequisites

- Azure CLI installed with GCC cloud configured
- Docker Desktop running
- Azure GCC subscription with permissions
- Managed identity enabled on the Web App

## Step 1: Set Azure CLI to GCC

```
az cloud set --name AzureUSGovernment
az login
az account set --subscription <subscription-id>
```

## Step 2: Configure `.env`

Use the GCC values in `.env.example`. Ensure these are set:
- `AZURE_AUTHORITY_HOST`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_DEPLOYMENT`
- `AZURE_OPENAI_API_VERSION`
- `AZURE_SEARCH_ENDPOINT`
- `AZURE_SEARCH_INDEX`
- `COSMOSDB_ENDPOINT`
- `COSMOSDB_KEY`
- `MICROSOFT_APP_ID`
- `BOT_FRAMEWORK_CHANNEL_SERVICE`
- `BOT_FRAMEWORK_OAUTH_URL`
- `ACR_NAME`
- `RESOURCE_GROUP`
- `LOCATION`
- `APP_SERVICE_PLAN`
- `WEBAPP_NAME`

## Step 3: Deploy to App Service

Run the PowerShell deployment script:

```
.\deploy-appservice.ps1
```

## Step 4: Configure Bot Messaging Endpoint

Set the bot messaging endpoint to:

```
https://<yourapp>.azurewebsites.us/api/messages
```

## Notes for GCC

- Ensure the managed identity has access to Azure OpenAI, Azure AI Search,
  Cosmos DB, and Key Vault.
- Use Gov endpoints for Bot Framework settings.
- If ACR admin credentials are required temporarily, set
  `USE_ACR_ADMIN_CREDENTIALS=true` in `.env`.
