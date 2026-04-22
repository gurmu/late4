# Microsoft Teams Deployment (Azure GCC)

## Prerequisites

- Azure GCC subscription
- Teams admin access in the same GCC tenant
- Bot registration in GCC

## Bot Registration (GCC)

1. Create a Bot resource in Azure GCC portal.
2. Set Bot Type to **User-Assigned Managed Identity**.
3. Copy the Microsoft App ID and App MSI Resource ID.
4. Update `.env`:

```
MICROSOFT_APP_ID=your-app-id
MICROSOFT_APP_PASSWORD=
BOT_TYPE=User-Assigned Managed Identity
APP_MSI_RESOURCE_ID=/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.ManagedIdentity/userAssignedIdentities/<name>
BOT_FRAMEWORK_CHANNEL_SERVICE=https://botframework.azure.us
BOT_FRAMEWORK_OAUTH_URL=https://login.microsoftonline.us/botframework/v1/.well-known/openidconfiguration
```

## Messaging Endpoint

Set the bot messaging endpoint to:

```
https://<yourapp>.azurewebsites.us/api/messages
```

## App Service (Linux) Multi-Container

Deploy using:

```
.\deploy-appservice.ps1
```

## App Service Identity + Permissions

In your Web App (App Service):

1. Enable Managed Identity (system-assigned OR attach the same user-assigned identity).
2. Grant that identity access to:
   - Azure AI Search (Search Index Data Reader)
   - Cosmos DB (Data Contributor)
   - Key Vault (Secrets Reader)

## Local Testing

If using a tunnel, ensure it is GCC-compliant and allowed by policy.

## Teams App Manifest

Update `teams_manifest/manifest.json`:

- `id` and `botId` must match the GCC App ID.
- Keep `validDomains` aligned to your hosting domain.
