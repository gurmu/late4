# Local Testing Guide (Azure GCC)

## Prerequisites

- Python 3.11+
- `.env` configured from `.env.example`
- Network access to Azure OpenAI (GCC) and Azure AI Search

## Quick Test

```
python src/main.py \
  --subject "VPN connection failure" \
  --description "Cannot connect to corporate VPN" \
  --email "user@company.com" \
  --phone "+1234567890"
```

Expected: A response based on KB context or `NO_KB_MATCH`.

## Teams Bot Local Test

```
python src/teams_server.py
```

Then POST a test message to `http://localhost:3978/api/messages`.

## Local Docker Compose

```
docker compose up --build
```

This will start:
- teams-bot on http://localhost:3978
- ivanti-api on http://localhost:8000
- nice-api on http://localhost:8001
