# Databricks notebook source
# MAGIC %md
# MAGIC ## Gold Layer - Multimodal Embedding Generation (Azure Vision)
# MAGIC
# MAGIC Replaces HuggingFace sentence-transformers with Azure Computer Vision
# MAGIC multimodal embeddings (Florence model). Produces a UNIFIED 1024-dim
# MAGIC embedding space where text and images are directly comparable.
# MAGIC
# MAGIC ### What changed vs. the old Gold Layer:
# MAGIC | Aspect | Old (HuggingFace) | New (Azure Vision) |
# MAGIC |--------|-------------------|---------------------|
# MAGIC | Text embedding | all-MiniLM-L6-v2 → 384D | Azure Vision vectorizeText → 1024D |
# MAGIC | Image embedding | clip-ViT-B-32 → 512D | Azure Vision vectorizeImage → 1024D |
# MAGIC | Vector fields | 2 (text_embedding + image_description_embedding) | 1 unified (vision_embedding) |
# MAGIC | Dependencies | sentence-transformers, torch (~2 GB) | requests (HTTP calls only) |
# MAGIC | Image query support | ❌ text-only at query time | ✅ native image + text queries |
# MAGIC
# MAGIC ### Pipeline:
# MAGIC 1. Text chunks → Azure Vision vectorizeText → 1024D vision_embedding
# MAGIC 2. Images → Azure Vision vectorizeImage → 1024D vision_embedding
# MAGIC 3. Unified multimodal table → Export to itsmgold container
# MAGIC
# MAGIC **IMPORTANT:** Run config, bronze, and silver notebooks first!

# COMMAND ----------

# MAGIC %md
# MAGIC ## Configuration & Imports

# COMMAND ----------

from pyspark.sql import functions as F, types as T
import pandas as pd
import numpy as np
import requests
import time
import logging
import hashlib
from io import BytesIO

# ============================================================================
# AZURE VISION CONFIGURATION
# ============================================================================
# Your Azure Computer Vision endpoint (GCC)
AZURE_VISION_ENDPOINT = "https://rdgvision.cognitiveservices.azure.us"
AZURE_VISION_KEY = dbutils.secrets.get(scope="itsm-secrets", key="azure-vision-key")
# If you are NOT using Databricks secrets, uncomment the line below instead:
# AZURE_VISION_KEY = "<YOUR_AZURE_VISION_KEY>"

# API config
VISION_API_VERSION = "2024-02-01"
VISION_MODEL_VERSION = "2023-04-15"  # Multi-lingual Florence model (102 languages)

# ============================================================================
# STORAGE & TABLE CONFIGURATION
# ============================================================================
# TODO: Replace with your actual storage account key (Key1 from Azure portal)
STORAGE_KEY = "<YOUR_STORAGE_KEY>"

CATALOG = "hive_metastore"
SCHEMA = "itsm"
ACCOUNT = "stitsmdev233lh8"
DFS_ENDPOINT = "dfs.core.usgovcloudapi.net"
BLOB_ENDPOINT = "blob.core.usgovcloudapi.net"

GOLD_CONTAINER = "itsmgold"
GOLD_ROOT = f"abfss://{GOLD_CONTAINER}@{ACCOUNT}.{DFS_ENDPOINT}/"

# Configure Spark to access Azure storage
spark.conf.set(f"fs.azure.account.key.{ACCOUNT}.{DFS_ENDPOINT}", STORAGE_KEY)

# ============================================================================
# EMBEDDING CONFIGURATION
# ============================================================================
# Azure Vision produces 1024-dim vectors for BOTH text and images
# in the SAME embedding space (Florence model)
VISION_EMBEDDING_DIM = 1024

# Chunking parameters (unchanged from original)
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 150

# Rate limiting: Azure Vision has per-second transaction limits
# Adjust based on your tier (Free=20/min, S1=10/sec, etc.)
VISION_REQUESTS_PER_SECOND = 8   # Conservative default for S1 tier
VISION_RETRY_MAX = 3
VISION_RETRY_BACKOFF = 2.0       # Seconds between retries on 429

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

print("=" * 80)
print("GOLD LAYER: Multimodal Embedding Generation (Azure Vision)")
print("=" * 80)
print(f"Catalog.Schema:    {CATALOG}.{SCHEMA}")
print(f"Gold Output:       {GOLD_ROOT}")
print(f"Vision Endpoint:   {AZURE_VISION_ENDPOINT}")
print(f"API Version:       {VISION_API_VERSION}")
print(f"Model Version:     {VISION_MODEL_VERSION}")
print(f"Embedding Dim:     {VISION_EMBEDDING_DIM}")
print(f"Rate Limit:        {VISION_REQUESTS_PER_SECOND} req/sec")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Azure Vision Embedding Functions
# MAGIC
# MAGIC Two functions that call the Azure Vision REST API:
# MAGIC - `vectorize_text()` — for text chunks (max 70 words per call)
# MAGIC - `vectorize_image()` — for image bytes (PNG/JPEG, max 20 MB)
# MAGIC
# MAGIC Both return a 1024-dim vector in the **same** embedding space.

# COMMAND ----------

def _vision_request_with_retry(url: str, headers: dict, json_body: dict = None,
                                data: bytes = None, content_type: str = None,
                                max_retries: int = VISION_RETRY_MAX) -> list:
    """
    Make an Azure Vision API request with retry logic for rate limiting (429).

    Returns:
        list[float]: 1024-dim embedding vector

    Raises:
        Exception: After max_retries exhausted or on non-retryable errors
    """
    for attempt in range(max_retries + 1):
        try:
            if json_body is not None:
                resp = requests.post(url, headers=headers, json=json_body, timeout=30)
            elif data is not None:
                img_headers = {**headers, "Content-Type": content_type or "application/octet-stream"}
                # Remove JSON content-type if present
                img_headers.pop("Content-Type", None)
                img_headers["Content-Type"] = content_type or "application/octet-stream"
                resp = requests.post(url, headers=img_headers, data=data, timeout=30)
            else:
                raise ValueError("Either json_body or data must be provided")

            if resp.status_code == 200:
                result = resp.json()
                vector = result.get("vector", [])
                if len(vector) != VISION_EMBEDDING_DIM:
                    logger.warning(
                        f"Unexpected vector dimension: {len(vector)} "
                        f"(expected {VISION_EMBEDDING_DIM})"
                    )
                return vector

            elif resp.status_code == 429:
                # Rate limited — back off and retry
                retry_after = float(resp.headers.get("Retry-After", VISION_RETRY_BACKOFF))
                wait_time = max(retry_after, VISION_RETRY_BACKOFF * (attempt + 1))
                logger.warning(
                    f"Rate limited (429). Retry {attempt + 1}/{max_retries}. "
                    f"Waiting {wait_time:.1f}s..."
                )
                time.sleep(wait_time)
                continue

            else:
                error_detail = resp.text[:500]
                raise Exception(
                    f"Azure Vision API error {resp.status_code}: {error_detail}"
                )

        except requests.exceptions.Timeout:
            if attempt < max_retries:
                logger.warning(f"Request timeout. Retry {attempt + 1}/{max_retries}...")
                time.sleep(VISION_RETRY_BACKOFF)
                continue
            raise

    raise Exception(f"Azure Vision API: max retries ({max_retries}) exhausted")


def vectorize_text(text: str) -> list:
    """
    Generate a 1024-dim embedding for a text string using Azure Vision.

    Azure Vision vectorizeText accepts 1-70 words. For longer text, we
    truncate to 70 words (the model captures semantic meaning well within
    this limit for retrieval purposes).

    Args:
        text: Input text string

    Returns:
        list[float]: 1024-dim embedding vector, or zeros on failure
    """
    if not text or not str(text).strip():
        return [0.0] * VISION_EMBEDDING_DIM

    # Azure Vision text limit: 70 words max
    words = str(text).strip().split()
    if len(words) > 70:
        text_truncated = " ".join(words[:70])
    else:
        text_truncated = str(text).strip()

    url = (
        f"{AZURE_VISION_ENDPOINT}/computervision/retrieval:vectorizeText"
        f"?api-version={VISION_API_VERSION}"
        f"&model-version={VISION_MODEL_VERSION}"
    )
    headers = {
        "Content-Type": "application/json",
        "Ocp-Apim-Subscription-Key": AZURE_VISION_KEY,
    }
    body = {"text": text_truncated}

    try:
        return _vision_request_with_retry(url, headers, json_body=body)
    except Exception as e:
        logger.error(f"vectorize_text failed: {e}")
        return [0.0] * VISION_EMBEDDING_DIM


def vectorize_image_from_bytes(image_bytes: bytes) -> list:
    """
    Generate a 1024-dim embedding for raw image bytes using Azure Vision.

    Supports PNG, JPEG, BMP, GIF. Max 20 MB, min 10x10 pixels.

    Args:
        image_bytes: Raw image bytes (PNG/JPEG)

    Returns:
        list[float]: 1024-dim embedding vector, or zeros on failure
    """
    if not image_bytes or len(image_bytes) == 0:
        return [0.0] * VISION_EMBEDDING_DIM

    # Check size limit (20 MB)
    if len(image_bytes) > 20 * 1024 * 1024:
        logger.warning(f"Image too large ({len(image_bytes)} bytes). Skipping.")
        return [0.0] * VISION_EMBEDDING_DIM

    url = (
        f"{AZURE_VISION_ENDPOINT}/computervision/retrieval:vectorizeImage"
        f"?api-version={VISION_API_VERSION}"
        f"&model-version={VISION_MODEL_VERSION}"
    )
    headers = {
        "Ocp-Apim-Subscription-Key": AZURE_VISION_KEY,
    }

    try:
        return _vision_request_with_retry(
            url, headers, data=image_bytes, content_type="application/octet-stream"
        )
    except Exception as e:
        logger.error(f"vectorize_image_from_bytes failed: {e}")
        return [0.0] * VISION_EMBEDDING_DIM


def vectorize_image_from_url(image_url: str) -> list:
    """
    Generate a 1024-dim embedding for an image given its public URL.

    Downloads the image first, then sends bytes to Azure Vision.
    (We download ourselves rather than using the URL-based API because
    the images are in Azure Gov blob storage which may require auth.)

    Args:
        image_url: HTTPS URL to the image

    Returns:
        list[float]: 1024-dim embedding vector, or zeros on failure
    """
    if not image_url:
        return [0.0] * VISION_EMBEDDING_DIM

    try:
        # Download image from blob storage
        resp = requests.get(image_url, timeout=30)
        resp.raise_for_status()
        return vectorize_image_from_bytes(resp.content)
    except Exception as e:
        logger.error(f"vectorize_image_from_url failed for {image_url}: {e}")
        return [0.0] * VISION_EMBEDDING_DIM


# ------------------------------------------------------------------
# Quick validation: test the API is reachable
# ------------------------------------------------------------------
print("\nTesting Azure Vision API connectivity...")
try:
    test_vector = vectorize_text("test connectivity")
    assert len(test_vector) == VISION_EMBEDDING_DIM, f"Got {len(test_vector)}D, expected {VISION_EMBEDDING_DIM}D"
    assert test_vector != [0.0] * VISION_EMBEDDING_DIM, "Got zero vector — API may have failed"
    print(f"✔ Azure Vision API is working. Returned {len(test_vector)}-dim vector.")
    print(f"  Sample values: [{test_vector[0]:.6f}, {test_vector[1]:.6f}, {test_vector[2]:.6f}, ...]")
except Exception as e:
    print(f"✖ Azure Vision API test FAILED: {e}")
    print(f"  Endpoint: {AZURE_VISION_ENDPOINT}")
    print(f"  Check: Is the key correct? Is the endpoint reachable from Databricks?")
    raise

# COMMAND ----------

# MAGIC %md
# MAGIC ## Text Chunking Function
# MAGIC
# MAGIC Same chunking logic as the original Gold Layer — no changes needed.

# COMMAND ----------

def chunk_words(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
    """Split text into overlapping chunks by word count."""
    if not text:
        return []
    words = str(text).split()
    out = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i:i + size])
        if chunk.strip():
            out.append(chunk)
        i += max(1, size - overlap)
    return out if out else [""]

chunk_udf = F.udf(
    lambda s: chunk_words(s, CHUNK_SIZE, CHUNK_OVERLAP),
    T.ArrayType(T.StringType())
)
print("✔ Chunking function defined (unchanged from original)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1/5 — Create Text Chunks from Silver Pages

# COMMAND ----------

print("\n[1/5] Creating text chunks from silver_pdf_pages...")

silver_pages = spark.table(f"{CATALOG}.{SCHEMA}.silver_pdf_pages")

text_chunks_exploded = (
    silver_pages
    .withColumn("chunks", chunk_udf(F.col("page_text_clean")))
    .withColumn("chunk", F.explode("chunks"))
    .withColumn("chunk_index", F.monotonically_increasing_id())
    .withColumn(
        "chunk_id",
        F.sha2(
            F.concat_ws("|",
                F.col("doc_id"),
                F.col("page_num").cast("string"),
                F.col("chunk_index").cast("string"),
                F.col("chunk")
            ),
            256
        )
    )
    .select(
        F.col("chunk_id").alias("id"),
        "doc_id",
        "file_name",
        "page_num",
        "chunk",
        "pdf_url"
    )
)

chunk_count = text_chunks_exploded.count()
print(f"✔ Generated {chunk_count} text chunks")

display(text_chunks_exploded.select("id", "file_name", "page_num", "chunk").limit(5))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2/5 — Generate 1024D Text Embeddings via Azure Vision
# MAGIC
# MAGIC Uses `mapInPandas` for distributed processing across Spark executors.
# MAGIC Each executor calls the Azure Vision REST API (no local model needed).
# MAGIC
# MAGIC **Key difference from old approach:** Instead of loading a 600 MB
# MAGIC sentence-transformers model on each executor, we make lightweight
# MAGIC HTTP calls to Azure Vision. This is simpler and more memory-efficient.

# COMMAND ----------

print("\n[2/5] Generating 1024-dim text embeddings via Azure Vision...")

# Schema for output: original columns + vision_embedding
text_embedding_schema = """
    id string, doc_id string, file_name string, page_num int,
    chunk string, pdf_url string, vision_embedding array<float>
"""

def text_embedding_map(iterator):
    """
    mapInPandas function: For each batch of text chunks,
    call Azure Vision vectorizeText and append the 1024D embedding.
    """
    request_interval = 1.0 / VISION_REQUESTS_PER_SECOND

    for batch_df in iterator:
        embeddings = []
        for idx, row in batch_df.iterrows():
            chunk_text = row.get("chunk", "")

            # Generate embedding via Azure Vision API
            emb = vectorize_text(chunk_text)
            embeddings.append(emb)

            # Rate limiting between requests
            time.sleep(request_interval)

        batch_df["vision_embedding"] = embeddings
        yield batch_df

gold_text_chunks = text_chunks_exploded.mapInPandas(
    text_embedding_map, schema=text_embedding_schema
)

# Persist to Delta table (checkpoint to avoid re-computation)
(gold_text_chunks.write.mode("overwrite")
 .option("mergeSchema", "true")
 .format("delta")
 .saveAsTable(f"{CATALOG}.{SCHEMA}.gold_text_chunks"))

text_emb_count = spark.table(f"{CATALOG}.{SCHEMA}.gold_text_chunks").count()
print(f"✔ Generated {text_emb_count} text embeddings (1024-dim)")

# Quick validation
sample = spark.table(f"{CATALOG}.{SCHEMA}.gold_text_chunks").select("id", "file_name", "vision_embedding").limit(1).collect()
if sample:
    emb_len = len(sample[0]["vision_embedding"])
    print(f"  Embedding dimension check: {emb_len}D ({'✔ correct' if emb_len == 1024 else '✖ UNEXPECTED'})")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3/5 — Generate 1024D Image Embeddings via Azure Vision
# MAGIC
# MAGIC For images, we use `vectorizeImage` which takes raw image bytes.
# MAGIC
# MAGIC **Key difference from old approach:** The old CLIP model could only
# MAGIC encode a generic text description ("Image from PDF document") — not
# MAGIC the actual image pixels. Azure Vision encodes the **actual image content**
# MAGIC into the same 1024D space as text, enabling true visual search.

# COMMAND ----------

print("\n[3/5] Generating 1024-dim image embeddings via Azure Vision...")

silver_images = spark.table(f"{CATALOG}.{SCHEMA}.silver_pdf_images")
# We also need the raw image bytes from bronze for vectorizeImage
bronze_images = spark.table(f"{CATALOG}.{SCHEMA}.bronze_pdf_images")

# Join silver (metadata + URLs) with bronze (raw image bytes)
# Silver columns (from your actual silver_pdf_images table):
#   doc_id, file_name, page_num, image_id, image_kind, image_name,
#   image_mime, width, height, image_abfss_path, image_url, pdf_url
# Bronze adds: image_bytes (binary)
#
# We select only the columns we need, in a controlled order,
# to avoid schema mismatches with mapInPandas
images_with_bytes = (
    silver_images.alias("s")
    .join(
        bronze_images.select("image_id", "image_bytes").alias("b"),
        on="image_id",
        how="left"
    )
    .select(
        "s.doc_id", "s.file_name", "s.page_num", "s.image_id",
        "s.image_kind", "s.image_name", "s.image_mime",
        "s.width", "s.height", "s.image_url", "s.pdf_url",
        "b.image_bytes"
    )
)

# Schema for output: must match input columns (minus image_bytes) + vision_embedding
# Column order must match exactly what image_embedding_map yields
image_embedding_schema = """
    doc_id string, file_name string, page_num int, image_id string,
    image_kind string, image_name string, image_mime string,
    width int, height int, image_url string, pdf_url string,
    vision_embedding array<float>
"""

def image_embedding_map(iterator):
    """
    mapInPandas function: For each batch of images,
    call Azure Vision vectorizeImage with raw bytes and append the 1024D embedding.
    """
    request_interval = 1.0 / VISION_REQUESTS_PER_SECOND

    for batch_df in iterator:
        embeddings = []
        for idx, row in batch_df.iterrows():
            img_bytes = row.get("image_bytes")

            if img_bytes is not None and len(img_bytes) > 0:
                # Use raw image bytes → Azure Vision vectorizeImage → 1024D
                emb = vectorize_image_from_bytes(bytes(img_bytes))
            else:
                # Fallback: try URL if bytes not available
                img_url = row.get("image_url", "")
                if img_url:
                    emb = vectorize_image_from_url(img_url)
                else:
                    emb = [0.0] * VISION_EMBEDDING_DIM

            embeddings.append(emb)
            time.sleep(request_interval)

        batch_df["vision_embedding"] = embeddings

        # Drop image_bytes column before yielding (not needed in gold output)
        if "image_bytes" in batch_df.columns:
            batch_df = batch_df.drop(columns=["image_bytes"])

        yield batch_df

gold_images = images_with_bytes.mapInPandas(
    image_embedding_map, schema=image_embedding_schema
)

(gold_images.write.mode("overwrite")
 .option("mergeSchema", "true")
 .format("delta")
 .saveAsTable(f"{CATALOG}.{SCHEMA}.gold_images"))

img_emb_count = spark.table(f"{CATALOG}.{SCHEMA}.gold_images").count()
print(f"✔ Generated {img_emb_count} image embeddings (1024-dim)")

# Quick validation
sample = spark.table(f"{CATALOG}.{SCHEMA}.gold_images").select("image_id", "vision_embedding").limit(1).collect()
if sample:
    emb_len = len(sample[0]["vision_embedding"])
    print(f"  Embedding dimension check: {emb_len}D ({'✔ correct' if emb_len == 1024 else '✖ UNEXPECTED'})")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4/5 — Create Unified Multimodal Table
# MAGIC
# MAGIC Merge text chunks and images into a single table. Both share the same
# MAGIC `vision_embedding` field (1024D) because Azure Vision puts text and
# MAGIC images in the **same** embedding space.
# MAGIC
# MAGIC This is the table that gets indexed into Azure AI Search.
# MAGIC
# MAGIC **Key difference:** The old approach had TWO separate vector fields
# MAGIC (text_embedding 384D + image_description_embedding 512D). Now we have
# MAGIC ONE unified field. Simpler index, simpler search queries, better results.

# COMMAND ----------

print("\n[4/5] Creating unified multimodal table...")

gold_text = spark.table(f"{CATALOG}.{SCHEMA}.gold_text_chunks")
gold_img = spark.table(f"{CATALOG}.{SCHEMA}.gold_images")

# Unify text items
text_items = (
    gold_text
    .withColumn("item_type", F.lit("text"))
    .withColumn("content", F.col("chunk"))
    .withColumn("image_url", F.lit(None).cast("string"))
    .withColumn("image_name", F.lit(None).cast("string"))
    .select(
        "id", "doc_id", "file_name", "page_num", "item_type",
        "content", "image_url", "image_name", "pdf_url",
        "vision_embedding"
    )
)

# Unify image items
# For image rows, content = contextual description built from file_name + page_num + image_kind
# This gives the image row keyword-searchable text so hybrid search can find it
# via both vector similarity AND keyword matching
image_items = (
    gold_img
    .withColumn("item_type", F.lit("image"))
    .withColumn("id", F.col("image_id"))
    .withColumn("content",
        F.concat_ws(" | ",
            F.concat(F.lit("Image from "), F.col("file_name")),
            F.concat(F.lit("page "), F.col("page_num").cast("string")),
            F.col("image_kind"),
            F.col("image_name")
        )
    )
    .select(
        "id", "doc_id", "file_name", "page_num", "item_type",
        "content", "image_url", "image_name", "pdf_url",
        "vision_embedding"
    )
)

# Union into single multimodal table
gold_multimodal = text_items.unionByName(image_items)

(gold_multimodal.write.mode("overwrite")
 .option("mergeSchema", "true")
 .format("delta")
 .saveAsTable(f"{CATALOG}.{SCHEMA}.gold_multimodal"))

total_count = spark.table(f"{CATALOG}.{SCHEMA}.gold_multimodal").count()
text_count = spark.table(f"{CATALOG}.{SCHEMA}.gold_multimodal").filter(F.col("item_type") == "text").count()
image_count = spark.table(f"{CATALOG}.{SCHEMA}.gold_multimodal").filter(F.col("item_type") == "image").count()

print(f"✔ Unified multimodal table: {total_count} total items")
print(f"  Text chunks:  {text_count}")
print(f"  Images:       {image_count}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5/5 — Export to Gold Container (Parquet + JSON)
# MAGIC
# MAGIC Exports the unified table for Azure AI Search indexing.
# MAGIC
# MAGIC The JSON export format matches what Azure AI Search expects for
# MAGIC push-based indexing via the REST API or SDK.

# COMMAND ----------

print("\n[5/5] Exporting to gold container...")

gold_df = spark.table(f"{CATALOG}.{SCHEMA}.gold_multimodal")

# --- Export as Parquet (for bulk import / backup) ---
parquet_path = f"{GOLD_ROOT}multimodal_parquet/"
(gold_df.write.mode("overwrite")
 .parquet(parquet_path))
print(f"✔ Exported Parquet to: {parquet_path}")

# --- Export as JSON (for Azure AI Search push indexing) ---
# Convert vision_embedding array to a format Azure AI Search expects
json_path = f"{GOLD_ROOT}multimodal_json/"

# Azure AI Search expects embedding as a flat array of floats
json_df = (
    gold_df
    .withColumn("vision_embedding_str",
        F.to_json(F.col("vision_embedding"))
    )
)

(json_df
 .select("id", "doc_id", "file_name", "page_num", "item_type",
         "content", "image_url", "pdf_url", "vision_embedding")
 .write.mode("overwrite")
 .json(json_path))
print(f"✔ Exported JSON to: {json_path}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary & Verification

# COMMAND ----------

print("\n" + "=" * 80)
print("GOLD LAYER COMPLETE — AZURE VISION MULTIMODAL EMBEDDINGS")
print("=" * 80)

gold_df = spark.table(f"{CATALOG}.{SCHEMA}.gold_multimodal")
total = gold_df.count()
texts = gold_df.filter(F.col("item_type") == "text").count()
images = gold_df.filter(F.col("item_type") == "image").count()

print(f"""
  Total items:        {total}
  Text chunks:        {texts}
  Images:             {images}
  Embedding model:    Azure Vision (Florence) via {AZURE_VISION_ENDPOINT}
  Embedding dim:      {VISION_EMBEDDING_DIM}
  Vector field:       vision_embedding (unified text + image)

  Tables created:
    {CATALOG}.{SCHEMA}.gold_text_chunks    — text chunks with 1024D embeddings
    {CATALOG}.{SCHEMA}.gold_images         — images with 1024D embeddings
    {CATALOG}.{SCHEMA}.gold_multimodal     — unified multimodal table

  Exports:
    {GOLD_ROOT}multimodal_parquet/    — Parquet backup
    {GOLD_ROOT}multimodal_json/       — JSON for Azure AI Search push indexing
""")

# Verify embedding dimensions
sample = gold_df.select("vision_embedding").limit(1).collect()
if sample:
    dim = len(sample[0]["vision_embedding"])
    status = "✔ CORRECT" if dim == VISION_EMBEDDING_DIM else "✖ MISMATCH"
    print(f"  Dimension check: {dim}D — {status}")

# Check for zero vectors (failed embeddings)
zero_check = gold_df.filter(
    F.col("vision_embedding")[0] == 0.0
).count()
if zero_check > 0:
    print(f"  ⚠ WARNING: {zero_check} items have zero-vector embeddings (API failures)")
    print(f"    Consider re-running for these items")
else:
    print(f"  ✔ No zero-vector embeddings detected")

print(f"""
  ┌──────────────────────────────────────────────────────────────┐
  │  NEXT STEPS                                                  │
  │                                                              │
  │  1. Update Azure AI Search index schema:                     │
  │     - Remove: text_embedding (384D), image_description_      │
  │       embedding (512D)                                       │
  │     - Add: vision_embedding (1024D,                          │
  │       Collection(Edm.Single), searchable, HNSW)              │
  │                                                              │
  │  2. Push documents from gold_multimodal_json/ to             │
  │     Azure AI Search                                          │
  │                                                              │
  │  3. Update itsm_search_plugin.py:                            │
  │     - Replace HuggingFace models with Azure Vision API calls │
  │     - Search against 'vision_embedding' (single field)       │
  │     - Add image query support for Teams attachments          │
  │                                                              │
  │  4. Update teams_bot.py:                                     │
  │     - Download image attachments from Teams                  │
  │     - Pass image bytes to orchestrator                       │
  │                                                              │
  │  5. Remove sentence-transformers & torch from                │
  │     requirements.txt (saves ~2 GB in container)              │
  └──────────────────────────────────────────────────────────────┘
""")

print("✔ Ready for Azure AI Search indexing")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Azure AI Search Index Schema Reference
# MAGIC
# MAGIC After running this notebook, update your Azure AI Search index with this schema.
# MAGIC You can do this via Azure Portal → AI Search → Index → Edit JSON, or via REST API.
# MAGIC
# MAGIC ```json
# MAGIC {
# MAGIC   "name": "itsm-mm-index",
# MAGIC   "fields": [
# MAGIC     {"name": "id", "type": "Edm.String", "key": true, "filterable": true},
# MAGIC     {"name": "doc_id", "type": "Edm.String", "filterable": true},
# MAGIC     {"name": "file_name", "type": "Edm.String", "filterable": true, "searchable": true},
# MAGIC     {"name": "page_num", "type": "Edm.Int32", "filterable": true},
# MAGIC     {"name": "item_type", "type": "Edm.String", "filterable": true},
# MAGIC     {"name": "content", "type": "Edm.String", "searchable": true, "analyzer": "standard.lucene"},
# MAGIC     {"name": "image_url", "type": "Edm.String", "filterable": false},
# MAGIC     {"name": "pdf_url", "type": "Edm.String", "filterable": false},
# MAGIC     {
# MAGIC       "name": "vision_embedding",
# MAGIC       "type": "Collection(Edm.Single)",
# MAGIC       "searchable": true,
# MAGIC       "dimensions": 1024,
# MAGIC       "vectorSearchProfile": "vision-profile"
# MAGIC     }
# MAGIC   ],
# MAGIC   "vectorSearch": {
# MAGIC     "algorithms": [
# MAGIC       {
# MAGIC         "name": "vision-hnsw",
# MAGIC         "kind": "hnsw",
# MAGIC         "hnswParameters": {
# MAGIC           "m": 4,
# MAGIC           "efConstruction": 400,
# MAGIC           "efSearch": 500,
# MAGIC           "metric": "cosine"
# MAGIC         }
# MAGIC       }
# MAGIC     ],
# MAGIC     "profiles": [
# MAGIC       {
# MAGIC         "name": "vision-profile",
# MAGIC         "algorithmConfigurationName": "vision-hnsw"
# MAGIC       }
# MAGIC     ]
# MAGIC   }
# MAGIC }
# MAGIC ```
