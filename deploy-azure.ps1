# ============================================================================
# Azure Container Deployment Script (PowerShell) - DEPRECATED
# ============================================================================
# This script used to deploy to Azure Container Instances (ACI).
# Use deploy-appservice.ps1 for Azure App Service (Linux) multi-container.
#
# Prerequisites:
#   - Azure CLI installed and logged in (az login)
#   - .env file configured with required environment variables
#   - Docker Desktop running
#   - Appropriate Azure permissions for resource creation
#
# For detailed instructions, see: CORPORATE_MIGRATION_GUIDE.md
# ============================================================================

# Stop script on any error
$ErrorActionPreference = "Stop"

Write-Host "This script is deprecated. Use deploy-appservice.ps1 instead." -ForegroundColor Red
exit 1

# ============================================================================
# Load Environment Variables from .env file
# ============================================================================
# Reads the .env file and sets environment variables for the current process
# This includes Azure AI configuration, bot credentials, and deployment settings

if (Test-Path .env) {
  Write-Host "Loading environment variables from .env file..." -ForegroundColor Cyan
  Get-Content .env | ForEach-Object {
    if ($_ -match '^([^#][^=]+)=(.*)$') {
      [Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
    }
  }
}
else {
  Write-Host "Error: .env file not found" -ForegroundColor Red
  Write-Host "Please copy .env.example to .env and configure your values" -ForegroundColor Red
  exit 1
}

# ============================================================================
# Configuration Variables
# ============================================================================
# These values are read from environment variables or use defaults
# You can override them in your .env file

$RESOURCE_GROUP = if ($env:RESOURCE_GROUP) { $env:RESOURCE_GROUP } else { "rg-itsm-multiagent" }
$LOCATION = if ($env:LOCATION) { $env:LOCATION } else { "usgovvirginia" }
$ACR_NAME = if ($env:ACR_NAME) { $env:ACR_NAME } else { "itsmacr$(Get-Date -Format 'yyyyMMddHHmmss')" }
$ACR_LOGIN_SERVER = "$ACR_NAME.azurecr.io"

Write-Host "============================================================================" -ForegroundColor Green
Write-Host "ITSM Multi-Agent Azure Deployment" -ForegroundColor Green
Write-Host "============================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Resource Group: $RESOURCE_GROUP"
Write-Host "Location: $LOCATION"
Write-Host "ACR Name: $ACR_NAME"
Write-Host ""

# ============================================================================
# Step 1: Create Azure Container Registry (ACR)
# ============================================================================
# ACR stores Docker images for deployment to Azure Container Instances
# This command is idempotent - it will use existing ACR if it already exists

Write-Host "Step 1: Creating Azure Container Registry..." -ForegroundColor Yellow

az acr create `
  --resource-group $RESOURCE_GROUP `
  --name $ACR_NAME `
  --sku Basic `
  --location $LOCATION `
  --admin-enabled true

Write-Host "ACR created/verified successfully" -ForegroundColor Green

# ============================================================================
# Retrieve ACR Credentials
# ============================================================================
# These credentials are needed to push Docker images to ACR
# Note: In production, consider using managed identities instead

$ACR_USERNAME = az acr credential show --name $ACR_NAME --query username -o tsv
$ACR_PASSWORD = az acr credential show --name $ACR_NAME --query passwords[0].value -o tsv

Write-Host "ACR credentials retrieved" -ForegroundColor Green

# ============================================================================
# Step 2: Build and Push Docker Images
# ============================================================================
# Builds three Docker images (Teams Bot, Ivanti API, NICE API) and pushes
# them to Azure Container Registry for deployment

Write-Host "Step 2: Building and pushing Docker images..." -ForegroundColor Yellow

# Login to ACR using Azure CLI
# This method is more reliable than manual docker login on Windows
Write-Host "Logging into ACR..." -ForegroundColor Yellow
az acr login --name $ACR_NAME
if ($LASTEXITCODE -ne 0) {
  Write-Host "Error: ACR login failed" -ForegroundColor Red
  Write-Host "Please ensure you are logged into Azure (az login)" -ForegroundColor Red
  exit 1
}
Write-Host "Successfully logged into ACR" -ForegroundColor Green

# Build and push Ivanti API
Write-Host "Building Ivanti API..."
docker build -t "${ACR_LOGIN_SERVER}/ivanti-api:latest" -f src/api/ivanti/Dockerfile .
if ($LASTEXITCODE -ne 0) { Write-Host "Error: Ivanti API build failed" -ForegroundColor Red; exit 1 }

docker push "${ACR_LOGIN_SERVER}/ivanti-api:latest"
if ($LASTEXITCODE -ne 0) { Write-Host "Error: Ivanti API push failed" -ForegroundColor Red; exit 1 }
Write-Host "Ivanti API pushed successfully" -ForegroundColor Green

# Build and push NICE API
Write-Host "Building NICE API..."
docker build -t "${ACR_LOGIN_SERVER}/nice-api:latest" -f src/api/nice_incontact/Dockerfile .
if ($LASTEXITCODE -ne 0) { Write-Host "Error: NICE API build failed" -ForegroundColor Red; exit 1 }

docker push "${ACR_LOGIN_SERVER}/nice-api:latest"
if ($LASTEXITCODE -ne 0) { Write-Host "Error: NICE API push failed" -ForegroundColor Red; exit 1 }
Write-Host "NICE API pushed successfully" -ForegroundColor Green

# Build and push Teams Bot
Write-Host "Building Teams Bot..."
docker build -t "${ACR_LOGIN_SERVER}/teams-bot:latest" -f Dockerfile .
if ($LASTEXITCODE -ne 0) { Write-Host "Error: Teams Bot build failed" -ForegroundColor Red; exit 1 }

docker push "${ACR_LOGIN_SERVER}/teams-bot:latest"
if ($LASTEXITCODE -ne 0) { Write-Host "Error: Teams Bot push failed" -ForegroundColor Red; exit 1 }
Write-Host "Teams Bot pushed successfully" -ForegroundColor Green

# ============================================================================
# Step 3: Create Azure Container Group YAML
# ============================================================================
Write-Host "Step 3: Creating container group configuration..." -ForegroundColor Yellow

# Using a string array to avoid here- string parsing issues
# Pre-build credential strings to ensure proper variable expansion
$credServerLine = "  - server: $ACR_LOGIN_SERVER"
$credUserLine = "    username: $ACR_USERNAME"
$credPassLine = "    password: $ACR_PASSWORD"

$yamlLines = @(
  "apiVersion: 2021-09-01",
  "location: $LOCATION",
  "name: itsm-multiagent",
  "properties:",
  "  containers:",
  "  - name: ivanti-api",
  "    properties:",
  "      image: ${ACR_LOGIN_SERVER}/ivanti-api:latest",
  "      resources:",
  "        requests:",
  "          cpu: 0.5",
  "          memoryInGb: 1.0",
  "      ports:",
  "      - port: 8000",
  "        protocol: TCP",
  "      environmentVariables:",
  "      - name: PORT",
  "        value: '8000'",
  "  - name: nice-api",
  "    properties:",
  "      image: ${ACR_LOGIN_SERVER}/nice-api:latest",
  "      resources:",
  "        requests:",
  "          cpu: 0.5",
  "          memoryInGb: 1.0",
  "      ports:",
  "      - port: 8001",
  "        protocol: TCP",
  "      environmentVariables:",
  "      - name: PORT",
  "        value: '8001'",
  "  - name: teams-bot",
  "    properties:",
  "      image: ${ACR_LOGIN_SERVER}/teams-bot:latest",
  "      resources:",
  "        requests:",
  "          cpu: 1.0",
  "          memoryInGb: 2.0",
  "      ports:",
  "      - port: 3978",
  "        protocol: TCP",
  "      environmentVariables:",
  "      - name: AZURE_AUTHORITY_HOST",
  "        value: '$env:AZURE_AUTHORITY_HOST'",
  "      - name: AZURE_OPENAI_ENDPOINT",
  "        value: '$env:AZURE_OPENAI_ENDPOINT'",
  "      - name: AZURE_OPENAI_DEPLOYMENT",
  "        value: '$env:AZURE_OPENAI_DEPLOYMENT'",
  "      - name: AZURE_OPENAI_API_VERSION",
  "        value: '$env:AZURE_OPENAI_API_VERSION'",
  "      - name: AZURE_SEARCH_ENDPOINT",
  "        value: '$env:AZURE_SEARCH_ENDPOINT'",
  "      - name: AZURE_SEARCH_INDEX",
  "        value: '$env:AZURE_SEARCH_INDEX'",
  "      - name: KB_TOP_K",
  "        value: '$env:KB_TOP_K'",
  "      - name: MICROSOFT_APP_ID",
  "        value: '$env:MICROSOFT_APP_ID'",
  "      - name: MICROSOFT_APP_PASSWORD",
  "        secureValue: '$env:MICROSOFT_APP_PASSWORD'",
  "      - name: BOT_FRAMEWORK_CHANNEL_SERVICE",
  "        value: '$env:BOT_FRAMEWORK_CHANNEL_SERVICE'",
  "      - name: BOT_FRAMEWORK_OAUTH_URL",
  "        value: '$env:BOT_FRAMEWORK_OAUTH_URL'",
  "      - name: IVANTI_API_URL",
  "        value: 'http://ivanti-api:8000'",
  "      - name: NICE_API_URL",
  "        value: 'http://nice-api:8001'",
  "      - name: PORT",
  "        value: '3978'",
  "  imageRegistryCredentials:",
  $credServerLine,
  $credUserLine,
  $credPassLine,
  "  ipAddress:",
  "    type: Public",
  "    ports:",
  "    - protocol: TCP",
  "      port: 3978",
  "    - protocol: TCP",
  "      port: 8000",
  "    - protocol: TCP",
  "      port: 8001",
  "    dnsNameLabel: itsm-bot-$(Get-Random -Minimum 1000 -Maximum 9999)",
  "  osType: Linux",
  "  restartPolicy: Always",
  "tags: {}",
  "type: Microsoft.ContainerInstance/containerGroups"
)

$yamlLines | Out-File -FilePath "container-group.yaml" -Encoding UTF8

Write-Host "Container group configuration created" -ForegroundColor Green

# ============================================================================
# Step 4: Deploy to Azure Container Instances
# ============================================================================
Write-Host "Step 4: Deploying to Azure Container Instances..." -ForegroundColor Yellow

az container create `
  --resource-group $RESOURCE_GROUP `
  --file container-group.yaml

Write-Host "Container instances deployed" -ForegroundColor Green

# Get the FQDN
$FQDN = az container show --resource-group $RESOURCE_GROUP --name itsm-multiagent --query ipAddress.fqdn -o tsv

Write-Host ""
Write-Host "============================================================================" -ForegroundColor Green
Write-Host "Deployment Complete!" -ForegroundColor Green
Write-Host "============================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Teams Bot Endpoint: http://${FQDN}:3978/api/messages"
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "1. Update Azure Bot messaging endpoint to: http://${FQDN}:3978/api/messages"
Write-Host "2. Test in Azure Bot Web Chat"
Write-Host "3. Deploy to Microsoft Teams"
Write-Host ""
Write-Host "To view logs:" -ForegroundColor Green
$logCmd = "az container logs --resource-group " + $RESOURCE_GROUP + " --name itsm-multiagent --container-name teams-bot"
Write-Host $logCmd
Write-Host ""
