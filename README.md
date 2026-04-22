# ITSM GCC Assistant

AI-powered ITSM assistant for Microsoft Teams running in Azure GCC.

## Overview

This project uses a code-first RAG approach:
- Azure OpenAI (Foundry model deployment) for responses
- Azure AI Search for ITSM knowledge retrieval
- Ivanti and NICE APIs for ticketing and callbacks
 - Optional vector search using text embeddings

## Quick Start

1. Copy `.env.example` to `.env` and set GCC values.
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Run locally:
   ```
   python src/main.py \
     --subject "VPN connection failure" \
     --description "Cannot connect to corporate VPN" \
     --email "user@company.com" \
     --phone "+1234567890"
   ```

## Docker Compose (Local)

```
docker compose up --build
```

## Azure App Service (Linux) Multi-Container

Deploy using:

```
.\deploy-appservice.ps1
```

This creates/updates a Web App and sets the Teams bot endpoint to:
`https://<yourapp>.azurewebsites.us/api/messages`

## Bot Identity (GCC Managed Identity)

Recommended bot configuration:
- Bot Type: User-Assigned Managed Identity
- Set `MICROSOFT_APP_ID` and `APP_MSI_RESOURCE_ID`
- Leave `MICROSOFT_APP_PASSWORD` empty
- Ensure Gov endpoints:
  - `BOT_FRAMEWORK_CHANNEL_SERVICE=https://botframework.azure.us`
  - `BOT_FRAMEWORK_OAUTH_URL=https://login.microsoftonline.us/botframework/v1/.well-known/openidconfiguration`

App Service requirements:
- Enable Managed Identity (system-assigned OR attach the same user-assigned identity)
- Grant identity access to:
  - Azure AI Search
  - Cosmos DB
  - Key Vault

Messaging endpoint (Bot Service → Configuration):
```
https://<yourapp>.azurewebsites.us/api/messages
```

## Semantic Kernel (SK) Environment Check

Use this script to verify your active Python environment can import the required SK symbols:

```
python scripts/check_sk_imports.py
```

If it fails, ensure `semantic-kernel==1.39.3` and `openai==1.109.1` are installed in the same Python environment used to run the app.

## Key Docs

- `AZURE_SETUP.md`
- `AZURE_CONTAINER_DEPLOYMENT.md`
- `RUNBOOK_APP_SERVICE.md`
- `TEAMS_DEPLOYMENT.md`
- `SECRETS_TEMPLATE.md`

## Project Structure

```

## Search Index Fields

This repo expects:
- `content` as the main searchable text field
- `file_name`, `page_num` for references
- `image_url` for visual references

Configure `KB_CONTENT_FIELD` and `KB_SEMANTIC_CONFIG` if needed.
ITSM/
  src/
    core/
    tools/
    main.py
    chat.py
    teams_bot.py
    teams_server.py
  knowledge-bases/
    itsm/
  teams_manifest/
  .env.example
  requirements.txt
```
