# ============================================================================
# RDG Chat — Azure App Service Multi-Container Deployment (GCC)
#
# USAGE:
#   .\deploy-appservice.ps1               # build images AND deploy
#   .\deploy-appservice.ps1 -SkipBuild    # deploy only (images already in ACR)
#
# Use -SkipBuild when:
#   - You built images off-VPN with build-acr.ps1 or az acr build manually
#   - You are on VPN (Zscaler blocks the blob-storage upload inside az acr build)
#   - You just want to re-deploy / update app settings without rebuilding
# ============================================================================
param(
    [switch]$SkipBuild
)

# Use Continue so that az CLI stderr warnings (Zscaler/urllib3) never crash
# the script.  Critical failures are caught explicitly via $LASTEXITCODE.
$ErrorActionPreference = "Continue"

# ---------------------------------------------------------------------------
# Helper: run az, discard all stderr (Zscaler noise), stop only on real failure
# ---------------------------------------------------------------------------
function Invoke-Az {
    param([string[]]$Arguments)
    $output = & az @Arguments 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: az $($Arguments -join ' ') failed (exit $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }
    return $output
}

# ---------------------------------------------------------------------------
# Helper: same but returns "" instead of stopping (for "does resource exist?")
# ---------------------------------------------------------------------------
function Invoke-AzQuery {
    param([string[]]$Arguments)
    $output = & az @Arguments 2>$null
    if ($LASTEXITCODE -ne 0) { return "" }
    return ($output | Out-String).Trim()
}

function Load-EnvFile {
    param([string]$Path = ".env")
    if (Test-Path $Path) {
        Write-Host "Loading environment variables from $Path..." -ForegroundColor Cyan
        Get-Content $Path | ForEach-Object {
            if ($_ -match '^([^#][^=]+)=(.*)$') {
                [Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
            }
        }
    }
}

Load-EnvFile

# GCC cloud + login
Invoke-Az @("cloud","set","--name","AzureUSGovernment")
az login 2>$null        # interactive prompt — suppress urllib3 noise only

if ($env:AZURE_SUBSCRIPTION_ID) {
    Invoke-Az @("account","set","--subscription",$env:AZURE_SUBSCRIPTION_ID)
}

# ---------------------------------------------------------------------------
# Configuration — all values from .env, with safe defaults
# ---------------------------------------------------------------------------
$RESOURCE_GROUP   = if ($env:RESOURCE_GROUP)    { $env:RESOURCE_GROUP }    else { "rg-itsm-multiagent-dev" }
$LOCATION         = if ($env:LOCATION)           { $env:LOCATION }           else { "usgovarizona" }
$ACR_NAME         = if ($env:ACR_NAME)           { $env:ACR_NAME }           else { "chitsm2" }
$APP_SERVICE_PLAN = if ($env:APP_SERVICE_PLAN)   { $env:APP_SERVICE_PLAN }   else { "asp-itsm-multiagent" }
$WEBAPP_NAME      = if ($env:WEBAPP_NAME)        { $env:WEBAPP_NAME }        else { "" }
$APP_SERVICE_SKU  = if ($env:APP_SERVICE_SKU)    { $env:APP_SERVICE_SKU }    else { "P1v3" }
# When skipping the build, use "latest" — the images already in ACR are tagged latest.
# When building, stamp a unique datetime tag so rollbacks are easy.
$TAG = if ($SkipBuild) { "latest" } else { Get-Date -Format "yyyyMMddHHmmss" }

if (-not $WEBAPP_NAME) {
    Write-Host "ERROR: WEBAPP_NAME is required in .env" -ForegroundColor Red
    exit 1
}

Write-Host "============================================================================" -ForegroundColor Green
Write-Host "RDG Chat - App Service Deployment (GCC)" -ForegroundColor Green
Write-Host "============================================================================" -ForegroundColor Green
Write-Host "Resource Group : $RESOURCE_GROUP"
Write-Host "Location       : $LOCATION"
Write-Host "ACR Name       : $ACR_NAME"
Write-Host "App Svc Plan   : $APP_SERVICE_PLAN"
Write-Host "Web App Name   : $WEBAPP_NAME"
Write-Host "Tag            : $TAG"
Write-Host ""

# ---- Resource group --------------------------------------------------------
Write-Host "Ensuring resource group $RESOURCE_GROUP..." -ForegroundColor Cyan
Invoke-Az @("group","create","--name",$RESOURCE_GROUP,"--location",$LOCATION) | Out-Null

# ---- ACR — look up by name only (ACR may be in a different resource group) -
# Do NOT pass --resource-group here; az finds it by name across all RGs.
Write-Host "Looking up ACR $ACR_NAME..." -ForegroundColor Cyan
$ACR_LOGIN_SERVER = (Invoke-Az @("acr","show","--name",$ACR_NAME,"--query","loginServer","-o","tsv")).Trim()
$ACR_ID           = (Invoke-Az @("acr","show","--name",$ACR_NAME,"--query","id","-o","tsv")).Trim()
Write-Host "ACR login server : $ACR_LOGIN_SERVER" -ForegroundColor Green

# ---- Build & push via ACR Tasks (az acr build) ----------------------------
if ($SkipBuild) {
    Write-Host "Skipping image build (-SkipBuild specified)." -ForegroundColor Yellow
    Write-Host "Using images already in ACR:" -ForegroundColor Yellow
    Write-Host "  $ACR_LOGIN_SERVER/ivanti-api:latest"
    Write-Host "  $ACR_LOGIN_SERVER/nice-api:latest"
    Write-Host "  $ACR_LOGIN_SERVER/teams-bot:latest"
} else {
    # Builds inside Azure — no local docker push needed, sidesteps Zscaler.
    # Requires off-VPN or DNS access to *.blob.core.usgovcloudapi.net.
    Write-Host "Building images via ACR Tasks (no local docker push required)..." -ForegroundColor Cyan

    Write-Host "  Building ivanti-api..." -ForegroundColor Cyan
    Invoke-Az @("acr","build","--registry",$ACR_NAME,"--image","ivanti-api:${TAG}","--image","ivanti-api:latest","-f","src/api/ivanti/Dockerfile",".")

    Write-Host "  Building nice-api..." -ForegroundColor Cyan
    Invoke-Az @("acr","build","--registry",$ACR_NAME,"--image","nice-api:${TAG}","--image","nice-api:latest","-f","src/api/nice_incontact/Dockerfile",".")

    Write-Host "  Building teams-bot..." -ForegroundColor Cyan
    Invoke-Az @("acr","build","--registry",$ACR_NAME,"--image","teams-bot:${TAG}","--image","teams-bot:latest","-f","Dockerfile",".")

    Write-Host "Images built and pushed to ACR:" -ForegroundColor Green
    Write-Host "  $ACR_LOGIN_SERVER/teams-bot:$TAG"
    Write-Host "  $ACR_LOGIN_SERVER/ivanti-api:$TAG"
    Write-Host "  $ACR_LOGIN_SERVER/nice-api:$TAG"
}

# ---- App Service Plan (in the app's resource group) -----------------------
Write-Host "Checking App Service Plan $APP_SERVICE_PLAN..." -ForegroundColor Cyan
$planExists = Invoke-AzQuery @("appservice","plan","show","--name",$APP_SERVICE_PLAN,"--resource-group",$RESOURCE_GROUP,"--query","name","-o","tsv")
if (-not $planExists) {
    Write-Host "  Creating App Service Plan..." -ForegroundColor Cyan
    Invoke-Az @("appservice","plan","create","--name",$APP_SERVICE_PLAN,"--resource-group",$RESOURCE_GROUP,"--location",$LOCATION,"--is-linux","--sku",$APP_SERVICE_SKU) | Out-Null
}

# ---- Web App ---------------------------------------------------------------
Write-Host "Checking Web App $WEBAPP_NAME..." -ForegroundColor Cyan
$webExists = Invoke-AzQuery @("webapp","show","--name",$WEBAPP_NAME,"--resource-group",$RESOURCE_GROUP,"--query","name","-o","tsv")
if (-not $webExists) {
    Write-Host "  Creating Web App..." -ForegroundColor Cyan
    Invoke-Az @("webapp","create","--name",$WEBAPP_NAME,"--resource-group",$RESOURCE_GROUP,"--plan",$APP_SERVICE_PLAN,"--deployment-container-image-name","${ACR_LOGIN_SERVER}/teams-bot:latest") | Out-Null
}

# ---- ACR pull credentials --------------------------------------------------
$USE_ACR_ADMIN = $env:USE_ACR_ADMIN_CREDENTIALS
if ($USE_ACR_ADMIN -and $USE_ACR_ADMIN.ToLower() -eq "true") {
    Write-Host "Using ACR admin credentials for image pull." -ForegroundColor Yellow
    $ACR_USERNAME = (Invoke-Az @("acr","credential","show","--name",$ACR_NAME,"--query","username","-o","tsv")).Trim()
    $ACR_PASSWORD = (Invoke-Az @("acr","credential","show","--name",$ACR_NAME,"--query","passwords[0].value","-o","tsv")).Trim()
    Invoke-Az @("webapp","config","container","set","--name",$WEBAPP_NAME,"--resource-group",$RESOURCE_GROUP,"--docker-registry-server-url","https://${ACR_LOGIN_SERVER}","--docker-registry-server-user",$ACR_USERNAME,"--docker-registry-server-password",$ACR_PASSWORD) | Out-Null
} else {
    $USER_ASSIGNED_IDENTITY_ID = $env:USER_ASSIGNED_IDENTITY_ID
    if ($USER_ASSIGNED_IDENTITY_ID) {
        Invoke-Az @("webapp","identity","assign","--name",$WEBAPP_NAME,"--resource-group",$RESOURCE_GROUP,"--identities",$USER_ASSIGNED_IDENTITY_ID) | Out-Null
        $principalId = (Invoke-Az @("identity","show","--ids",$USER_ASSIGNED_IDENTITY_ID,"--query","principalId","-o","tsv")).Trim()
    } else {
        $principalId = (Invoke-Az @("webapp","identity","assign","--name",$WEBAPP_NAME,"--resource-group",$RESOURCE_GROUP,"--query","principalId","-o","tsv")).Trim()
    }
    Invoke-Az @("role","assignment","create","--assignee-object-id",$principalId,"--role","AcrPull","--scope",$ACR_ID) | Out-Null
}

# ---- Prepare App Service compatible compose file --------------------------
# Substitute ${ACR_LOGIN_SERVER} and ${IMAGE_TAG:-latest} with real values.
# The compose file has already had ports/networks/restart removed.
$composeRaw = Get-Content docker-compose.yml -Raw
$composeRaw = $composeRaw -replace '\$\{ACR_LOGIN_SERVER(?::-[^}]*)?\}', $ACR_LOGIN_SERVER
$composeRaw = $composeRaw -replace '\$\{IMAGE_TAG(?::-[^}]*)?\}',        $TAG
$composePath = "scripts/.compose.appservice.yml"
New-Item -ItemType Directory -Force -Path (Split-Path $composePath) | Out-Null
# Write UTF-8 WITHOUT BOM — PowerShell's Set-Content -Encoding UTF8 adds a BOM
# which breaks Azure App Service's YAML parser.
$absoluteComposePath = [System.IO.Path]::GetFullPath($composePath)
[System.IO.File]::WriteAllText($absoluteComposePath, $composeRaw, (New-Object System.Text.UTF8Encoding $false))

Invoke-Az @("webapp","config","container","set","--name",$WEBAPP_NAME,"--resource-group",$RESOURCE_GROUP,"--multicontainer-config-type","compose","--multicontainer-config-file",$composePath) | Out-Null

# ---- App settings ----------------------------------------------------------
Write-Host "Applying app settings..." -ForegroundColor Cyan
$settings = @(
    "WEBSITES_PORT=3978",
    "PORT=3978",
    "IVANTI_API_URL=http://ivanti-api:8000",
    "NICE_API_URL=http://nice-api:8001",
    "AZURE_AUTHORITY_HOST=$env:AZURE_AUTHORITY_HOST",
    "AZURE_OPENAI_ENDPOINT=$env:AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_DEPLOYMENT=$env:AZURE_OPENAI_DEPLOYMENT",
    "AZURE_OPENAI_API_VERSION=$env:AZURE_OPENAI_API_VERSION",
    "AZURE_OPENAI_API_KEY=$env:AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT=$env:AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
    "AZURE_SEARCH_ENDPOINT=$env:AZURE_SEARCH_ENDPOINT",
    "AZURE_SEARCH_INDEX=$env:AZURE_SEARCH_INDEX",
    "AZURE_SEARCH_KEY=$env:AZURE_SEARCH_KEY",
    "KB_TOP_K=$env:KB_TOP_K",
    "KB_CONTENT_FIELD=$env:KB_CONTENT_FIELD",
    "KB_SEMANTIC_CONFIG=$env:KB_SEMANTIC_CONFIG",
    "COSMOSDB_ENDPOINT=$env:COSMOSDB_ENDPOINT",
    "COSMOSDB_KEY=$env:COSMOSDB_KEY",
    "COSMOSDB_DATABASE=$env:COSMOSDB_DATABASE",
    "COSMOSDB_CONTAINER=$env:COSMOSDB_CONTAINER",
    "MICROSOFT_APP_ID=$env:MICROSOFT_APP_ID",
    "MICROSOFT_APP_PASSWORD=$env:MICROSOFT_APP_PASSWORD",
    "BOT_TYPE=$env:BOT_TYPE",
    "APP_MSI_RESOURCE_ID=$env:APP_MSI_RESOURCE_ID",
    "BOT_FRAMEWORK_CHANNEL_SERVICE=$env:BOT_FRAMEWORK_CHANNEL_SERVICE",
    "BOT_FRAMEWORK_OAUTH_URL=$env:BOT_FRAMEWORK_OAUTH_URL",
    "IVANTI_BASE_URL=$env:IVANTI_BASE_URL",
    "IVANTI_API_KEY=$env:IVANTI_API_KEY",
    "NICE_BASE_URL=$env:NICE_BASE_URL",
    "NICE_ACCESS_KEY_ID=$env:NICE_ACCESS_KEY_ID",
    "NICE_ACCESS_KEY_SECRET=$env:NICE_ACCESS_KEY_SECRET",
    "AZURE_VISION_ENDPOINT=$env:AZURE_VISION_ENDPOINT",
    "AZURE_VISION_KEY=$env:AZURE_VISION_KEY",
    "AZURE_STORAGE_ACCOUNT_NAME=$env:AZURE_STORAGE_ACCOUNT_NAME",
    "AZURE_STORAGE_ACCOUNT_KEY=$env:AZURE_STORAGE_ACCOUNT_KEY",
    "AZURE_STORAGE_SAS_EXPIRY_HOURS=$env:AZURE_STORAGE_SAS_EXPIRY_HOURS"
)

Invoke-Az (@("webapp","config","appsettings","set","--name",$WEBAPP_NAME,"--resource-group",$RESOURCE_GROUP,"--settings") + $settings) | Out-Null

Invoke-Az @("webapp","restart","--name",$WEBAPP_NAME,"--resource-group",$RESOURCE_GROUP) | Out-Null

Write-Host "============================================================================" -ForegroundColor Green
Write-Host "Deployment Complete!" -ForegroundColor Green
Write-Host "============================================================================" -ForegroundColor Green
Write-Host "Messaging Endpoint : https://${WEBAPP_NAME}.azurewebsites.us/api/messages" -ForegroundColor Cyan
Write-Host "Health Endpoint    : https://${WEBAPP_NAME}.azurewebsites.us/health" -ForegroundColor Cyan
Write-Host ""
Write-Host "Stream live logs:" -ForegroundColor Green
Write-Host "  az webapp log tail --name $WEBAPP_NAME --resource-group $RESOURCE_GROUP"

Remove-Item $composePath -ErrorAction SilentlyContinue
