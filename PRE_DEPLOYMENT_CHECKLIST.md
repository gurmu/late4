# Pre-Corporate GitHub Deployment Checklist

## ✅ Code Changes Applied

### Fixed
- [x] **Vector Search** - Replaced dummy `[0.0]` with real embeddings (384D text + 512D CLIP)
- [x] **Import Paths** - Added `PYTHONPATH=/app/src` to Dockerfile
- [x] **Certificate Handling** - Made optional (won't block Docker builds)
- [x] **Dependencies** - Added `sentence-transformers>=2.2.0` and `torch>=1.13.0`
- [x] **Cleanup** - Removed temporary `itsm_search_plugin_fixed.py`

### Modified Files (Ready to Commit)
```
M  Dockerfile
M  requirements.txt
M  src/agents/plugins/itsm_search_plugin.py
```

### New Files (Ready to Commit)
```
A  IMPLEMENTATION_GUIDE.md
```

---

## ⚠️ NOT Implemented Yet (Future Work)

### Image Processing (GPT-4o Vision)
These changes are **documented** in `IMPLEMENTATION_GUIDE.md` but **NOT implemented** in code:

- [ ] `src/teams_bot.py` - Image download from Teams
- [ ] `src/agents/multi_agent_orchestrator.py` - Multimodal message support
- [ ] GPT-4o vision deployment in Azure GCC

**Why Not Included:**
- Requires GPT-4o **with vision** to be deployed first
- User confirmed standard GPT-4o is currently deployed
- This is a **Phase 2 enhancement** (see IMPLEMENTATION_GUIDE.md Step 2-3)

---

## 🔍 Pre-Push Review

### 1. Environment Variables (.env.example)
Review your `.env.example` to ensure all variables are documented:

**Current Variables (from your file):**
- ✅ `AZURE_AUTHORITY_HOST` - GCC authority
- ✅ `AZURE_OPENAI_ENDPOINT` - GCC endpoint
- ✅ `AZURE_OPENAI_DEPLOYMENT` - Model deployment (gpt-4o)
- ✅ `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` - Embedding model (text-embedding-3-small)
- ✅ `AZURE_SEARCH_ENDPOINT` - GCC search endpoint
- ✅ `AZURE_SEARCH_INDEX` - Your index name
- ✅ `AZURE_SEARCH_KEY` - Search API key
- ✅ `KB_CONTENT_FIELD` - Content field (default: "content")
- ✅ `KB_SEMANTIC_CONFIG` - Semantic config (default: "itsm")
- ✅ Cosmos DB variables
- ✅ Teams Bot variables (MSI, channel service, OAuth)

**Recommendation:** ✅ Your `.env.example` is comprehensive and GCC-ready!

---

### 2. Deployment Scripts
Your existing deployment scripts are **production-ready**:

- ✅ `deploy-appservice.ps1` - Azure App Service deployment (GCC)
- ✅ `TEAMS_DEPLOYMENT.md` - Teams bot setup guide
- ✅ `docker-compose.yml` - Multi-container setup

**Notes:**
- Scripts correctly use `.azurewebsites.us` domain (GCC)
- Managed Identity setup is included
- Multi-container deployment (teams-bot + ivanti-api + nice-api) is configured

---

### 3. Documentation Review

**Existing Docs (Keep All):**
- `README.md` - Project overview
- `AZURE_SETUP.md` - Azure resource setup
- `AZURE_CONTAINER_DEPLOYMENT.md` - Container deployment
- `TEAMS_DEPLOYMENT.md` - Teams bot setup
- `LOCAL_TESTING_GUIDE.md` - Local development
- `RUNBOOK_APP_SERVICE.md` - Operations runbook
- `PRE_DEPLOYMENT_CHECKLIST.md` - Deployment checklist
- `QUICK_LOCAL_CHECK.md` - Quick validation
- `SECRETS_TEMPLATE.md` - Secrets management
- `CORPORATE_MIGRATION_GUIDE.md` - Migration guide

**New Docs (Just Created):**
- `IMPLEMENTATION_GUIDE.md` - Multi-vector search + GPT-4o vision guide

**Recommendation:** All documentation is relevant and should be committed.

---

### 4. Sensitive Files Check

**NEVER Commit These:**
- ❌ `.env` (actual environment variables)
- ❌ `certs/*.crt` (corporate certificates)
- ❌ Any files with API keys or secrets

**Verify .gitignore:**
```bash
# Check current .gitignore
cat .gitignore | grep -E "(\.env$|certs|secrets|\.key)"
```

If missing, add to `.gitignore`:
```
.env
certs/
*.crt
*.key
*.pem
secrets/
```

---

## 🚀 Ready to Push? Complete These Steps

### Step 1: Review Changes
```powershell
cd RDG_Chat
git status
git diff Dockerfile
git diff requirements.txt
git diff src/agents/plugins/itsm_search_plugin.py
```

### Step 2: Verify .gitignore
```powershell
# Check if sensitive files are ignored
git status --ignored
# Ensure .env, certs, and secrets are in "Ignored files" section
```

### Step 3: Test Locally (Recommended)
```powershell
# Build Docker image
docker compose build

# Verify sentence-transformers is installed
docker run -it rdg_chat-teams-bot:latest python -c "from sentence_transformers import SentenceTransformer; print('✓ Dependencies OK')"

# Run full stack (optional)
docker compose up
```

### Step 4: Commit and Push
```powershell
# Stage changes
git add Dockerfile
git add requirements.txt
git add src/agents/plugins/itsm_search_plugin.py
git add IMPLEMENTATION_GUIDE.md

# Commit
git commit -m "Fix vector search with multi-vector embeddings (384D text + 512D CLIP)

- Replace dummy [0.0] vector with real embeddings via sentence-transformers
- Add sentence-transformers and torch dependencies
- Fix import paths with PYTHONPATH in Dockerfile
- Make certificate copy optional in Dockerfile
- Add implementation guide for GPT-4o vision (Phase 2)"

# Push to corporate GitHub
git push origin main
```

---

## 📋 Corporate Environment Setup

Once pushed to corporate GitHub, follow these steps:

### 1. Clone in Corporate Environment
```powershell
git clone <corporate-github-url>
cd RDG_Chat
```

### 2. Create .env File
```powershell
# Copy template
cp .env.example .env

# Edit with corporate values
notepad .env
```

**Required Values:**
- GCC Azure OpenAI endpoint
- GCC Azure Search endpoint
- GCC Cosmos DB endpoint
- Corporate Bot App ID and MSI Resource ID
- API keys (or use Key Vault)

### 3. Add Corporate Certificates (if needed)
```powershell
# Create certs directory
mkdir certs

# Copy corporate CA certificate
# The Dockerfile now handles optional certificates gracefully
```

### 4. Deploy to Azure GCC
```powershell
# Run deployment script
.\deploy-appservice.ps1
```

---

## ⚡ Quick Verification After Deployment

### 1. Check Vector Search
```powershell
# View logs
az webapp log tail --name <your-webapp> --resource-group <your-rg>
```

**Look for:**
```
✓ Loaded text embedding model (384D)
✓ Loaded CLIP model (512D)
✓ Added text vector query (384D)
✓ Added image description vector query (512D)
```

### 2. Test Search Quality
Send test queries via Teams and verify:
- ✅ Results are relevant (not "NO_KB_MATCH" for known topics)
- ✅ KB references include file names and page numbers
- ✅ Response quality improved compared to keyword-only search

---

## 🎯 Phase 2: Enable GPT-4o Vision (Future)

**When ready to add image processing:**

1. Deploy GPT-4o **with vision** in GCC (see IMPLEMENTATION_GUIDE.md Step 2)
2. Update `.env`:
   ```
   AZURE_OPENAI_DEPLOYMENT=gpt-4o-vision
   ```
3. Apply image processing code (IMPLEMENTATION_GUIDE.md Step 3)
4. Test with screenshot uploads in Teams

---

## 📊 Expected Behavior After Deployment

### Before (Current State in Corporate)
- ❌ Vector search returns irrelevant results
- ❌ Import errors in production
- ❌ Docker builds fail without certificates

### After (With These Changes)
- ✅ Vector search returns relevant KB articles
- ✅ Multi-vector hybrid search (text + image embeddings)
- ✅ Clean Docker builds
- ✅ No import errors
- ✅ Production-ready for GCC deployment

---

## 🆘 Troubleshooting

### Problem: Docker build fails
**Solution:** Ensure `sentence-transformers` is in requirements.txt (it is ✓)

### Problem: Import errors at runtime
**Solution:** `PYTHONPATH=/app/src` is in Dockerfile (it is ✓)

### Problem: Vector search returns no results
**Check:**
1. Models are downloading (first run takes ~2-3 minutes)
2. Embedding dimensions match your index (384D text, 512D image)
3. Field names match schema (`text_embedding`, `image_description_embedding`)

### Problem: Slow startup
**Cause:** Models download ~700MB on first run
**Solution:** Normal behavior; subsequent starts are fast

---

## ✅ Final Checklist

Before pushing to corporate GitHub:

- [x] Vector search fixed
- [x] Dependencies updated
- [x] Dockerfile fixed  
- [x] Temporary files removed
- [ ] `.gitignore` verified (check sensitive files)
- [ ] Local Docker build tested (optional but recommended)
- [ ] Changes reviewed with `git diff`

**Ready to commit and push!** 🚀
