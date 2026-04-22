# Azure App Service (Linux) Multi-Container Runbook (GCC)

This runbook assumes Azure Government cloud and a Bot Service configured for
User-Assigned Managed Identity.

## 1) Prereqs

- Azure CLI with GCC cloud
- Docker Desktop
- Repo `.env` populated from `.env.example`

## 2) Required Azure Resources

- Resource Group
- Azure Container Registry (ACR)
- App Service Plan (Linux)
- Web App (Linux, multi-container)
- Bot Service (User-Assigned Managed Identity)

## 3) Identity + Access

Web App identity must have:
- Azure AI Search: Search Index Data Reader
- Cosmos DB: Data Contributor
- Key Vault: Secrets Reader
- ACR: AcrPull

If using user-assigned identity, set:
- `BOT_TYPE=User-Assigned Managed Identity`
- `APP_MSI_RESOURCE_ID=/subscriptions/.../userAssignedIdentities/<name>`

## 4) Deploy (CLI)

```
az cloud set --name AzureUSGovernment
az login
az account set --subscription <subscription-id>

.\deploy-appservice.ps1
```

The script builds and pushes 3 images (teams-bot, ivanti-api, nice-api),
updates the Web App multi-container config, sets app settings, and restarts.

## 5) Bot Messaging Endpoint

In Bot Service → Configuration → Messaging endpoint:

```
https://<yourapp>.azurewebsites.us/api/messages
```

## 6) Health Checks

- Bot: `https://<yourapp>.azurewebsites.us/health`
- Ivanti API (internal): `http://ivanti-api:8000/health`
- NICE API (internal): `http://nice-api:8001/health`

## 7) Logs

```
az webapp log tail --name <webapp> --resource-group <rg>
```

## 8) Common Troubleshooting

- 502 / container failed to start: check `WEBSITES_PORT=3978` and bot binding to `PORT`.
- Bot not responding: verify Bot Messaging Endpoint is HTTPS and correct path `/api/messages`.
- Image pull errors: ensure identity has `AcrPull` or set `USE_ACR_ADMIN_CREDENTIALS=true`.
- GCC endpoints missing: verify `BOT_FRAMEWORK_CHANNEL_SERVICE` and `BOT_FRAMEWORK_OAUTH_URL`.
