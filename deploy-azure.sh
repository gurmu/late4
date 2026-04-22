#!/bin/bash

# ============================================================================
# Azure Container Deployment Script - DEPRECATED
# ============================================================================
# This script used to deploy to Azure Container Instances (ACI).
# Use deploy-appservice.ps1 for Azure App Service (Linux) multi-container.
# Prerequisites: Azure CLI installed and logged in
# ============================================================================

set -e  # Exit on error

echo -e "${RED}This script is deprecated. Use deploy-appservice.ps1 instead.${NC}"
exit 1

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
else
    echo -e "${RED}Error: .env file not found${NC}"
    exit 1
fi

# Configuration
RESOURCE_GROUP="${RESOURCE_GROUP:-ashuvs}"
LOCATION="${LOCATION:-usgovvirginia}"
ACR_NAME="${ACR_NAME:-itsmacr$(date +%s)}"
ACR_LOGIN_SERVER="${ACR_NAME}.azurecr.io"

echo -e "${GREEN}============================================================================${NC}"
echo -e "${GREEN}ITSM Multi-Agent Azure Deployment${NC}"
echo -e "${GREEN}============================================================================${NC}"
echo ""
echo "Resource Group: $RESOURCE_GROUP"
echo "Location: $LOCATION"
echo "ACR Name: $ACR_NAME"
echo ""

# ============================================================================
# Step 1: Create Azure Container Registry
# ============================================================================
echo -e "${YELLOW}Step 1: Creating Azure Container Registry...${NC}"

# Check if ACR exists
if az acr show --name $ACR_NAME --resource-group $RESOURCE_GROUP &> /dev/null; then
    echo "ACR $ACR_NAME already exists"
else
    az acr create \
        --resource-group $RESOURCE_GROUP \
        --name $ACR_NAME \
        --sku Basic \
        --location $LOCATION \
        --admin-enabled true
    echo -e "${GREEN}✓ ACR created successfully${NC}"
fi

# Get ACR credentials
ACR_USERNAME=$(az acr credential show --name $ACR_NAME --query username -o tsv)
ACR_PASSWORD=$(az acr credential show --name $ACR_NAME --query passwords[0].value -o tsv)

echo -e "${GREEN}✓ ACR credentials retrieved${NC}"

# ============================================================================
# Step 2: Build and Push Docker Images
# ============================================================================
echo -e "${YELLOW}Step 2: Building and pushing Docker images...${NC}"

# Login to ACR
echo $ACR_PASSWORD | docker login $ACR_LOGIN_SERVER --username $ACR_USERNAME --password-stdin

# Build and push Ivanti API
echo "Building Ivanti API..."
docker build -t $ACR_LOGIN_SERVER/ivanti-api:latest -f src/api/ivanti/Dockerfile .
docker push $ACR_LOGIN_SERVER/ivanti-api:latest
echo -e "${GREEN}✓ Ivanti API pushed${NC}"

# Build and push NICE API
echo "Building NICE API..."
docker build -t $ACR_LOGIN_SERVER/nice-api:latest -f src/api/nice_incontact/Dockerfile .
docker push $ACR_LOGIN_SERVER/nice-api:latest
echo -e "${GREEN}✓ NICE API pushed${NC}"

# Build and push Teams Bot
echo "Building Teams Bot..."
docker build -t $ACR_LOGIN_SERVER/teams-bot:latest -f Dockerfile .
docker push $ACR_LOGIN_SERVER/teams-bot:latest
echo -e "${GREEN}✓ Teams Bot pushed${NC}"

# ============================================================================
# Step 3: Deploy to Azure Container Instances
# ============================================================================
echo -e "${YELLOW}Step 3: Deploying to Azure Container Instances...${NC}"

# Create container group with all services
az container create \
    --resource-group $RESOURCE_GROUP \
    --name itsm-multiagent \
    --location $LOCATION \
    --registry-login-server $ACR_LOGIN_SERVER \
    --registry-username $ACR_USERNAME \
    --registry-password $ACR_PASSWORD \
    --dns-name-label itsm-bot-${RANDOM} \
    --ports 3978 8000 8001 \
    --cpu 2 \
    --memory 4 \
    --environment-variables \
        AZURE_AUTHORITY_HOST=$AZURE_AUTHORITY_HOST \
        AZURE_OPENAI_ENDPOINT=$AZURE_OPENAI_ENDPOINT \
        AZURE_OPENAI_DEPLOYMENT=$AZURE_OPENAI_DEPLOYMENT \
        AZURE_OPENAI_API_VERSION=$AZURE_OPENAI_API_VERSION \
        AZURE_SEARCH_ENDPOINT=$AZURE_SEARCH_ENDPOINT \
        AZURE_SEARCH_INDEX=$AZURE_SEARCH_INDEX \
        KB_TOP_K=$KB_TOP_K \
        MICROSOFT_APP_ID=$MICROSOFT_APP_ID \
        BOT_FRAMEWORK_CHANNEL_SERVICE=$BOT_FRAMEWORK_CHANNEL_SERVICE \
        BOT_FRAMEWORK_OAUTH_URL=$BOT_FRAMEWORK_OAUTH_URL \
        IVANTI_API_URL=http://ivanti-api:8000 \
        NICE_API_URL=http://nice-api:8001 \
        PORT=3978 \
    --secure-environment-variables \
        MICROSOFT_APP_PASSWORD=$MICROSOFT_APP_PASSWORD \
    --image $ACR_LOGIN_SERVER/teams-bot:latest

echo -e "${GREEN}✓ Container instances deployed${NC}"

# Get the FQDN
FQDN=$(az container show --resource-group $RESOURCE_GROUP --name itsm-multiagent --query ipAddress.fqdn -o tsv)

echo ""
echo -e "${GREEN}============================================================================${NC}"
echo -e "${GREEN}Deployment Complete!${NC}"
echo -e "${GREEN}============================================================================${NC}"
echo ""
echo "Teams Bot Endpoint: https://$FQDN:3978/api/messages"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "1. Update Azure Bot messaging endpoint to: https://$FQDN:3978/api/messages"
echo "2. Test in Azure Bot Web Chat"
echo "3. Deploy to Microsoft Teams"
echo ""
echo -e "${GREEN}To view logs:${NC}"
echo "az container logs --resource-group $RESOURCE_GROUP --name itsm-multiagent"
echo ""
