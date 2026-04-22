# Azure GCC Setup Guide (OpenAI + AI Search)

This project uses a code-first RAG approach in Azure GCC:
- Azure OpenAI (Foundry model deployment) for reasoning and responses
- Azure AI Search for ITSM knowledge base retrieval
- Managed identity for authentication

## Prerequisites

- Azure GCC subscription access
- Azure OpenAI resource deployed in GCC
- Azure AI Search service in GCC with index `itsm-mm-index`
- Managed identity enabled for the compute hosting this app

## Step 1: Configure Managed Identity Access

Grant the managed identity access to:
- Azure OpenAI resource (Cognitive Services User or equivalent)
- Azure AI Search (Search Index Data Reader)
- Cosmos DB (Data Contributor)
- Key Vault (Secrets Reader)

## Step 2: Configure Environment Variables

Copy `.env.example` to `.env` and fill in:

```
AZURE_AUTHORITY_HOST=https://login.microsoftonline.us

AZURE_OPENAI_ENDPOINT=https://itsmhub.openai.azure.us/
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_OPENAI_API_VERSION=2024-10-01-preview

AZURE_SEARCH_ENDPOINT=https://your-search-service.search.azure.us/
AZURE_SEARCH_INDEX=itsm-mm-index
KB_TOP_K=5
```

## Step 3: Verify Search Index Content

Your `itsm-mm-index` should contain ITSM knowledge content in a text field.
Set `KB_CONTENT_FIELD=content` (or your actual field name).
If semantic search is enabled, set `KB_SEMANTIC_CONFIG` to your configuration name.
If vector search is enabled, set `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` to your embedding deployment.

## Step 4: Run a Local Test

```
python src/main.py \
  --subject "VPN connection failure" \
  --description "Cannot connect to corporate VPN" \
  --email "user@company.com" \
  --phone "+1234567890"
```

Expected: A classification response based only on KB content, or `NO_KB_MATCH`.
