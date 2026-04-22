# Quick Local Check (GCC)

## File/Config Check

```
python --version
Test-Path .env
Test-Path src/main.py
Test-Path src/teams_server.py
Test-Path requirements.txt
```

## Required Env Vars

Verify these exist in `.env`:
- `AZURE_AUTHORITY_HOST`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_DEPLOYMENT`
- `AZURE_OPENAI_API_VERSION`
- `AZURE_SEARCH_ENDPOINT`
- `AZURE_SEARCH_INDEX`
- `MICROSOFT_APP_ID`
- `MICROSOFT_APP_PASSWORD`
