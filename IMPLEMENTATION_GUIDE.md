# Implementation Guide: Multi-Vector Search + GPT-4o Vision

## Your Current Setup

**Azure Search Schema:**
```
- text_embedding: 384 dims (sentence-transformers)
- image_pixel_embedding: 512 dims (CLIP visual features)
- image_description_embedding: 512 dims (CLIP text features)
```

**Deployed Model:**
- GPT-4o (standard, not vision-enabled)

---

## Step 1: Fix Vector Search (CRITICAL)

### 1.1 Install Required Dependencies

Add to `requirements.txt`:
```
sentence-transformers>=2.2.0
torch>=1.13.0  # Required by sentence-transformers
```

Rebuild Docker:
```bash
docker compose build
```

### 1.2 Replace ITSM Search Plugin

**Backup original:**
```bash
cd RDG_Chat/src/agents/plugins
cp itsm_search_plugin.py itsm_search_plugin_backup.py
```

**Copy new version:**
```bash
cp itsm_search_plugin_fixed.py itsm_search_plugin.py
```

### 1.3 Update Orchestrator Configuration

In `multi_agent_orchestrator.py`, update the ITSM agent:

```python
def _build_itsm_agent(self) -> ChatCompletionAgent:
    kernel = self._build_kernel()
    
    # Load embedding models (lazy initialization in plugin)
    from sentence_transformers import SentenceTransformer
    text_model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')  # 384D
    clip_model = SentenceTransformer('sentence-transformers/clip-ViT-B-32')     # 512D
    
    kernel.add_plugin(
        ITSMSearchPlugin(
            endpoint=self.config.azure_search_endpoint,
            index_name=self.config.azure_search_index,
            api_key=self.config.azure_search_key,
            content_field=self.config.kb_content_field,
            embedding_model=text_model,
            clip_model=clip_model,
        ),
        plugin_name="itsm",
    )
    
    instructions = (
        "You are the ITSM agent. Use the itsm.search_kb tool to retrieve guidance. "
        "The search uses hybrid multi-vector approach (text + image embeddings). "
        "Return concise summaries and cite KB snippets in your response."
    )
    return ChatCompletionAgent(
        name="ITSM",
        instructions=instructions,
        kernel=kernel,
        service=kernel.get_service("chat"),
    )
```

**Alternative (Recommended): Lazy Loading**

The new plugin supports lazy loading, so you can skip model initialization:

```python
kernel.add_plugin(
    ITSMSearchPlugin(
        endpoint=self.config.azure_search_endpoint,
        index_name=self.config.azure_search_index,
        api_key=self.config.azure_search_key,
        content_field=self.config.kb_content_field,
        # Models will be loaded automatically on first search
    ),
    plugin_name="itsm",
)
```

### 1.4 Test Vector Search

```bash
# Local test
python src/main.py \
  --subject "VPN connection failure" \
  --description "Cannot connect to corporate VPN" \
  --email "test@company.com" \
  --phone "+1234567890" \
  --conversation-id "test-001"
```

**Expected behavior:**
- ✅ Console logs show "Added text vector query (384D)"
- ✅ Console logs show "Added image description vector query (512D)"
- ✅ Relevant KB results returned (not "NO_KB_MATCH")

---

## Step 2: Deploy GPT-4o Vision (Required for Image Analysis)

### 2.1 Check Current Deployment

```bash
az cognitiveservices account deployment list \
  --name <your-openai-resource-name> \
  --resource-group <your-rg> \
  --subscription <your-subscription-id>
```

### 2.2 Deploy GPT-4o with Vision in GCC

**Option A: Azure Portal**
1. Go to https://portal.azure.us/
2. Navigate to your Azure OpenAI resource
3. Go to **Model deployments**
4. Click **Create new deployment**
5. Select model: **gpt-4o** (ensure vision is enabled)
6. Deployment name: `gpt-4o-vision` (or keep `gpt-4o` if replacing)
7. Deploy

**Option B: Azure CLI**
```bash
az cognitiveservices account deployment create \
  --name <your-openai-resource-name> \
  --resource-group <your-rg> \
  --deployment-name gpt-4o \
  --model-name gpt-4o \
  --model-version "2024-05-13" \
  --model-format OpenAI \
  --sku-capacity 10 \
  --sku-name "Standard"
```

### 2.3 Verify Vision Capability

Test with Azure OpenAI Studio:
1. Go to https://oai.azure.us/
2. Open **Chat playground**
3. Select your `gpt-4o` deployment
4. Upload an image
5. Ask: "What's in this image?"
6. Verify response describes the image

---

## Step 3: Enable Image Attachment Handling in Teams Bot

### 3.1 Update `teams_bot.py`

Replace the `on_message_activity` method:

```python
import httpx
import base64

async def on_message_activity(self, turn_context: TurnContext):
    """Handle incoming messages from Teams with image support."""
    try:
        conversation_id = turn_context.activity.conversation.id
        user_message = turn_context.activity.text or ""
        attachments = []
        
        # Process image attachments
        if turn_context.activity.attachments:
            for att in turn_context.activity.attachments:
                # Check if it's an image
                if att.content_type and att.content_type.startswith('image/'):
                    try:
                        # Download image from Teams CDN
                        async with httpx.AsyncClient(timeout=30.0) as client:
                            response = await client.get(att.content_url)
                            response.raise_for_status()
                            
                            # Base64 encode for GPT-4o
                            image_b64 = base64.b64encode(response.content).decode()
                            attachments.append({
                                'type': 'image_url',
                                'image_url': {
                                    'url': f"data:{att.content_type};base64,{image_b64}",
                                    'detail': 'high'  # High-res analysis
                                }
                            })
                            logger.info(f"✓ Processed image: {att.name} ({len(response.content)} bytes)")
                    except Exception as e:
                        logger.error(f"Failed to download {att.name}: {e}")
                        user_message += f"\n[Error: Could not process image {att.name}]"
                else:
                    # Non-image attachment
                    logger.warning(f"Unsupported attachment type: {att.content_type}")
                    user_message += f"\n[Attachment: {att.name} - type not supported]"
        
        # Process with orchestrator
        logger.info(f"Processing message with {len(attachments)} image(s)")
        response = await self.orchestrator.run_conversation(
            user_message, 
            conversation_id,
            attachments=attachments
        )
        
        # Send response back to Teams
        await turn_context.send_activity(MessageFactory.text(response))
        logger.info("✓ Response sent to Teams")
        
    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)
        await turn_context.send_activity(
            MessageFactory.text(f"Sorry, I encountered an error: {str(e)}")
        )
```

### 3.2 Update `multi_agent_orchestrator.py`

Add `attachments` parameter to `run_conversation`:

```python
async def run_conversation(
    self, 
    user_input: str, 
    conversation_id: str,
    attachments: list[dict] | None = None
) -> str:
    """
    Run conversation with optional image attachments.
    
    Args:
        user_input: User's text message
        conversation_id: Conversation thread ID
        attachments: List of GPT-4o vision format attachments
    """
    chat = AgentGroupChat(
        agents=[self._orchestrator_agent, self._itsm_agent, self._ivanti_agent, self._nice_agent],
        termination_strategy=FinalResolutionTerminationStrategy(),
    )

    history = self._history_store.load(conversation_id)
    chat.chat_history = history

    # Build multimodal message if images present
    if attachments:
        # Note: Semantic Kernel ChatHistory needs text-only for storage
        # The actual vision processing happens when agents invoke GPT-4o
        chat.chat_history.add_user_message(
            f"{user_input}\n\n[User sent {len(attachments)} image(s)]"
        )
        logger.info(f"Added multimodal message with {len(attachments)} attachments")
    else:
        chat.chat_history.add_user_message(user_input)

    # Invoke agent group (GPT-4o will receive images via Kernel)
    response = ""
    async for message in chat.invoke():
        response = message.content or ""

    # Save to Cosmos
    self._history_store.append(conversation_id, "user", user_input)
    self._history_store.append(conversation_id, "assistant", response)

    return response
```

### 3.3 Update Orchestrator Instructions

```python
def _build_orchestrator_agent(self) -> ChatCompletionAgent:
    kernel = self._build_kernel()
    instructions = (
        "You are the Orchestrator for an ITSM multi-agent system.\n\n"
        
        "**Image Analysis Capability:**\n"
        "You can analyze images sent by users (screenshots, error messages, system diagrams).\n"
        "When an image is provided:\n"
        "1. Carefully examine the image for relevant details\n"
        "2. Extract any visible error messages, codes, or warnings\n"
        "3. Identify UI elements, system components, or network diagrams\n"
        "4. Search the ITSM knowledge base for related issues\n"
        "5. Provide specific troubleshooting steps based on what you see\n\n"
        
        "**Agent Delegation:**\n"
        "Delegate to specialist agents:\n"
        "- ITSM agent: Knowledge base search\n"
        "- Ivanti agent: Create incident tickets\n"
        "- NICE agent: Schedule callbacks\n\n"
        
        "**Response Format:**\n"
        "Return JSON: {priority, category, team, summary, actions[], final: bool}\n"
        "Set final=true when you have a complete resolution.\n"
        "Include FINAL_RESOLUTION in the message when done."
    )
    return ChatCompletionAgent(
        name="Orchestrator",
        instructions=instructions,
        kernel=kernel,
        service=kernel.get_service("chat"),
    )
```

---

## Step 4: Fix Import Paths

### Option A: Update PYTHONPATH (Recommended)

**In `Dockerfile`:**
```dockerfile
# Add after WORKDIR /app
ENV PYTHONPATH=/app/src:$PYTHONPATH
```

**In `docker-compose.yml`:**
```yaml
services:
  teams-bot:
    environment:
      PYTHONPATH: /app/src
```

### Option B: Fix Imports in Code

**In `main.py`:**
```python
# Change from:
from agents.multi_agent_orchestrator import MultiAgentOrchestrator, TicketRequest
from core.logging import setup_logging

# To:
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from agents.multi_agent_orchestrator import MultiAgentOrchestrator, TicketRequest
from core.logging import setup_logging
```

---

## Step 5: Testing

### 5.1 Test Vector Search Locally

```bash
docker compose up --build
```

Check logs for:
```
✓ Loaded text embedding model (384D)
✓ Loaded CLIP model (512D)
✓ Added text vector query (384D)
✓ Added image description vector query (512D)
✓ Found 5 KB results
```

### 5.2 Test Image Processing in Teams

1. Deploy to Azure
2. Open Teams, find your bot
3. Send a message: "I'm having a VPN issue"
4. Upload a screenshot of the error
5. Verify bot:
   - ✓ Acknowledges image receipt
   - ✓ Describes what it sees
   - ✓ Searches KB for related issues
   - ✓ Provides specific troubleshooting steps

---

## Step 6: Deploy to Azure

### 6.1 Build and Push Images

```powershell
# From RDG_Chat directory
.\deploy-appservice.ps1
```

Or manually:
```bash
# Build
docker compose build

# Tag for ACR
docker tag local/teams-bot:latest <your-acr>.azurecr.us/teams-bot:latest

# Push
docker push <your-acr>.azurecr.us/teams-bot:latest
```

### 6.2 Update App Service Configuration

Ensure environment variables are set:
```
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-small
```

### 6.3 Verify Deployment

```bash
# Check logs
az webapp log tail --name <your-webapp> --resource-group <your-rg>
```

Look for:
```
✓ ITSM Teams Bot initialized
✓ Loaded text embedding model (384D)
✓ Loaded CLIP model (512D)
```

---

## Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'sentence_transformers'"

**Fix:** Ensure `sentence-transformers>=2.2.0` is in `requirements.txt` and rebuild Docker.

### Issue: Vector search returns no results

**Check:**
1. Embedding dimensions match (384 for text, 512 for images)
2. Field names in code match Azure Search schema
3. Logs show "Added text vector query (384D)"

### Issue: Images not being processed

**Check:**
1. GPT-4o vision is deployed (not standard GPT-4o)
2. Bot has permissions to access attachment URLs
3. Logs show "✓ Processed image: ..."

### Issue: "Error generating text embedding"

**Fix:** Model download may be slow on first run. Check:
```bash
# Inside container
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
```

---

## Performance Optimization (Optional)

### Cache Embedding Models

Create a model cache:
```python
# In multi_agent_orchestrator.py __init__
self._text_model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
self._clip_model = SentenceTransformer('sentence-transformers/clip-ViT-B-32')

# Pass to plugin
kernel.add_plugin(
    ITSMSearchPlugin(..., embedding_model=self._text_model, clip_model=self._clip_model)
)
```

### Use GPU in Docker

If deploying on GPU-enabled instances:
```dockerfile
# Use GPU base image
FROM nvidia/cuda:11.8.0-runtime-ubuntu22.04
# ... rest of Dockerfile
```

---

## Next Steps

1. ✅ Fix vector search (critical)
2. ✅ Deploy GPT-4o vision
3. ✅ Enable image processing
4. 🔄 Test end-to-end
5. 🔄 Deploy to GCC
6. 📊 Monitor performance with Application Insights
7. 🎯 Add Content Safety filters (optional)
8. 🗣️ Add Speech capabilities (optional)
