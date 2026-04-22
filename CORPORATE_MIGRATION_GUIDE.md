# Corporate Migration Guide (Azure GCC)

## Overview

This solution runs in Azure GCC using:
- Azure OpenAI (Foundry model deployment)
- Azure AI Search for ITSM KB retrieval
- Managed identity for auth
- Microsoft Teams bot in GCC

## Prerequisites

- Azure GCC subscription
- Azure OpenAI + Azure AI Search resources
- Managed identity on compute
- Teams bot registration in GCC tenant

## Configuration

Update `.env` based on `.env.example`:
- `AZURE_AUTHORITY_HOST`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_DEPLOYMENT`
- `AZURE_OPENAI_API_VERSION`
- `AZURE_SEARCH_ENDPOINT`
- `AZURE_SEARCH_INDEX`
- `MICROSOFT_APP_ID`
- `MICROSOFT_APP_PASSWORD`
- `BOT_FRAMEWORK_CHANNEL_SERVICE`
- `BOT_FRAMEWORK_OAUTH_URL`

## Deployment

1. Set Azure CLI to GCC:
   ```
   az cloud set --name AzureUSGovernment
   az login
   ```
2. Deploy containers:
   ```
   .\deploy-azure.ps1
   ```
3. Update Teams bot messaging endpoint with the deployed URL.

## Verification

- Run `python src/main.py` with a known ITSM query.
- In Teams, confirm the bot returns KB-based answers.
