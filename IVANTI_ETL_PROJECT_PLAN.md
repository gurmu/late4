# Ivanti ETL Pipeline — Project Management Plan
### ITSM Chatbot | Azure DevOps Work Items

---

## Overview

| Field | Detail |
|-------|--------|
| **Project** | ITSM Chatbot — Ivanti Data Ingestion Automation |
| **Pipeline Type** | Option B — Automated ETL (Databricks Scheduled Workflow) |
| **Processing Engine** | Azure Databricks |
| **Storage** | Azure Blob Storage (Bronze / Silver / Gold) |
| **Cloud** | Azure Government Cloud (GCC) |
| **Area Path** | `ITSM-Chatbot\Data-Engineering` |

---

## Architecture Summary

```
[On-Prem Sources]          [Pre-Production — Azure Databricks]             [Gold Outputs]
─────────────────          ────────────────────────────────────             ──────────────
Ivanti / HEAT         ──►  ETL Extract (secure connectors)
Knowledge Docs/Images ──►      │
Operational Logs      ──►      ▼
                           Bronze (raw/itsm/*, raw/docs/*, raw/logs/*)
                               │
                               ▼
                           Silver (itsm_tickets.parquet, kb_docs.parquet, kb_images/*)
                               │
                               ▼
                           QA Gate (Dedup, PII Scrub, Type Fixes)
                               │
                               ▼
                           Gold ──► corpus_text.parquet
                                ──► corpus_images/*
                                ──► metadata.parquet
```

**Automation mechanism:** Single Databricks Workflow (`ivanti-itsm-etl-daily`) chains all pipeline stages on a daily `cron` at 02:00 AM UTC. No human triggers the pipeline in production.

---

## Delivery Phases

| Phase | Epics | Milestone | Sprints |
|-------|-------|-----------|---------|
| **Phase 1 — Foundation** | Epic 1 + Epic 2 | Connectivity established, Bronze landing automated | Sprint 1–2 |
| **Phase 2 — Transform** | Epic 3 | Silver outputs clean, PII scrubbed, QA gate running | Sprint 2–3 |
| **Phase 3 — Gold Corpus** | Epic 4 | Chunked text + images + metadata ready | Sprint 3 |
| **Phase 4 — Automate** | Epic 5 | Databricks Workflow running on schedule, alerts live | Sprint 4 |

---

## Priority Reference

| Level | Label | Meaning |
|-------|-------|---------|
| 1 | Critical | Blocker — nothing downstream works without this |
| 2 | High | Required for phase completion |
| 3 | Medium | Important but not a blocker |
| 4 | Low | Nice to have |

---

---

# EPIC 1 — Secure On-Prem Data Extraction

```
Work Item Type : Epic
Title          : Secure On-Prem Data Extraction from Ivanti/HEAT and Knowledge Sources
Area Path      : ITSM-Chatbot\Data-Engineering
Priority       : 1 (Critical)
Story Points   : 34
```

**Description:**
Establish authenticated, automated connectivity from on-prem Ivanti/HEAT system, Knowledge Docs & Images file share, and Operational Logs to Azure Blob Storage. This epic is the entry point of the entire ETL pipeline. Nothing downstream can run until this extraction layer is stable and automated.

**Acceptance Criteria:**
- All three on-prem sources (Ivanti API, Docs/Images, Logs) can be extracted without manual credential entry
- Extraction runs automatically via Databricks Job scheduler
- All credentials stored in Azure Key Vault GCC — zero hardcoded secrets
- Delta/incremental extraction supported — only pulls records changed since last run
- Failed extractions trigger an alert and do not silently produce empty output

---

## User Story 1.1 — Ivanti HEAT API Connector

```
Work Item Type : User Story
Title          : Build authenticated Ivanti HEAT OData API connector with delta extraction
Parent Epic    : Epic 1 — Secure On-Prem Data Extraction
Area Path      : ITSM-Chatbot\Data-Engineering
Priority       : 1 (Critical)
Story Points   : 13
Iteration      : Sprint 1
```

**Description:**
As a data engineer, I need a Python-based Ivanti HEAT OData connector that authenticates securely and extracts Incidents, Problems, Changes, and KB Articles with delta support, so that only new or modified records are pulled on each scheduled run without re-processing the full dataset.

**Acceptance Criteria:**
- Connector authenticates using API key retrieved from Azure Key Vault (no hardcoded keys)
- Supports OData `$filter` using `lastModifiedDate` for incremental extraction
- Supports OData `$skip/$top` pagination — handles record sets larger than API page size
- Extracts four object types: Incidents, Problems, Changes, KB Articles
- Implements retry logic: 3 retries with exponential backoff on HTTP 429/5xx errors
- Returns structured Python dataclass objects per record type
- Unit tests cover: auth success, auth failure, pagination, retry on 429, empty result set

### Task 1.1.1

```
Title       : Create ivanti_connector.py — OData GET client with Key Vault auth
Assigned To : Data Engineer
Estimate    : 2 days
Priority    : 1 (Critical)
```

**Description:**
Create `src/etl/extract/ivanti_connector.py`.
- Use `azure-identity DefaultAzureCredential` to fetch `IVANTI_API_KEY` from Key Vault
- Implement async GET with `aiohttp` against OData endpoint: `https://tss.keypoint.us.com/HEAT/api/odata/businessobject`
- Add `Authorization` header: `"rest_api_key={key}"`
- Return raw JSON response per page

**Acceptance Criteria:**
- Auth reads from Key Vault, never from env file directly
- GET request includes correct OData headers (`Accept: application/json`)
- Function signature: `async def get_records(object_type, filter_expr, top, skip) -> dict`

---

### Task 1.1.2

```
Title       : Implement OData pagination handler
Assigned To : Data Engineer
Estimate    : 1 day
Priority    : 1 (Critical)
```

**Description:**
Add pagination loop to `ivanti_connector.py`.
- Loop using `$skip` + `$top` (page size = 500)
- Continue until response record count < page size (last page)
- Yield pages as async generator to avoid loading full dataset into memory

**Acceptance Criteria:**
- Tested against an object type with > 1000 records
- Generator yields one page at a time (not a full list)
- Stops correctly on final partial page

---

### Task 1.1.3

```
Title       : Implement delta extraction cursor using lastModifiedDate filter
Assigned To : Data Engineer
Estimate    : 1 day
Priority    : 1 (Critical)
```

**Description:**
Add delta extraction logic:
- Read `last_successful_run` timestamp from cursor store (Azure Blob file: `etl-state/cursors/{object_type}.json`)
- Build OData `$filter`: `"lastModifiedDate gt {cursor_timestamp}"`
- After successful extraction, update cursor file with current run timestamp
- Full-load mode: pass `--full-load` flag to ignore cursor and extract all records

**Acceptance Criteria:**
- On second run, only records modified after first run are returned
- Cursor file is only updated after all pages are successfully received
- Full-load mode extracts all records regardless of cursor

---

### Task 1.1.4

```
Title       : Implement retry logic and rate-limit handling
Assigned To : Data Engineer
Estimate    : 0.5 days
Priority    : 1 (Critical)
```

**Description:**
Add resilience to `ivanti_connector.py`:
- Retry on HTTP 429 (rate limit) and 5xx errors
- Maximum 3 retries with exponential backoff: 2s, 4s, 8s
- Log each retry attempt with attempt number and wait time
- Raise extraction exception after 3 failed attempts

**Acceptance Criteria:**
- Unit test simulates 429 response — confirms retry with backoff
- Unit test simulates 3x failure — confirms exception raised
- No infinite retry loops

---

### Task 1.1.5

```
Title       : Write unit tests for Ivanti connector
Assigned To : Data Engineer
Estimate    : 1 day
Priority    : 2 (High)
```

**Description:**
Write pytest test suite in `tests/test_ivanti_connector.py`. Cover: successful auth, Key Vault read, pagination (3 pages), delta filter applied, retry on 429, exception after 3 failures, empty response handling.

**Acceptance Criteria:**
- All tests pass in CI
- Minimum 80% code coverage on `ivanti_connector.py`
- Tests use mocked HTTP responses (no live API calls in CI)

---

## User Story 1.2 — Knowledge Docs & Images Extractor

```
Work Item Type : User Story
Title          : Build file extractor for on-prem Knowledge Docs and Images
Parent Epic    : Epic 1 — Secure On-Prem Data Extraction
Area Path      : ITSM-Chatbot\Data-Engineering
Priority       : 1 (Critical)
Story Points   : 8
Iteration      : Sprint 1
```

**Description:**
As a data engineer, I need a Python extractor that reads Knowledge Docs (PDF, DOCX, HTML) and Images (PNG, JPG) from an on-prem file share and copies them to Azure Blob Bronze landing zone, skipping files already landed using content hash deduplication.

**Acceptance Criteria:**
- Reads from on-prem SFTP or file share path configured via Key Vault secret
- Supports PDF, DOCX, HTML, PNG, JPG file types — rejects all others with a log warning
- Deduplicates using SHA-256 content hash — skips files already in Bronze
- Preserves original file name and folder structure in Bronze destination
- Runs as part of the same Databricks Job as the Ivanti connector

### Task 1.2.1

```
Title       : Create kb_file_extractor.py — file share reader with SFTP/SMB support
Assigned To : Data Engineer
Estimate    : 1.5 days
Priority    : 1 (Critical)
```

**Description:**
Create `src/etl/extract/kb_file_extractor.py`.
- Connect to on-prem file share using credentials from Key Vault (support SFTP via `paramiko` or SMB via `smbprotocol`)
- Walk directory tree, collect all files matching allowed extensions
- Return list of `(file_path, file_name, file_size, last_modified)` tuples
- File type whitelist: `.pdf`, `.docx`, `.html`, `.png`, `.jpg`, `.jpeg`

**Acceptance Criteria:**
- Connects without hardcoded credentials
- Returns correct file list for a test directory
- Ignores files with non-whitelisted extensions and logs skipped files

---

### Task 1.2.2

```
Title       : Implement content-hash deduplication for file extractor
Assigned To : Data Engineer
Estimate    : 1 day
Priority    : 1 (Critical)
```

**Description:**
Add deduplication to `kb_file_extractor.py`:
- Compute SHA-256 hash of each file before uploading
- Check against hash manifest stored in Azure Blob: `etl-state/kb_hash_manifest.json`
- Skip upload if hash already exists in manifest
- Update manifest with new hash after successful upload

**Acceptance Criteria:**
- Re-running extractor on unchanged files skips all uploads
- Changed files (different hash) are re-uploaded and manifest updated
- Manifest file is never corrupted by concurrent writes (use blob lease or single-writer pattern)

---

### Task 1.2.3

```
Title       : Upload deduplicated files to Bronze blob raw/docs/ and raw/docs/images/
Assigned To : Data Engineer
Estimate    : 0.5 days
Priority    : 1 (Critical)
```

**Description:**
After deduplication check, upload files to Bronze:
- Text documents → `raw/docs/{YYYY-MM-DD}/{filename}`
- Image files → `raw/docs/images/{YYYY-MM-DD}/{filename}`

Use `azure-storage-blob BlobClient` with Managed Identity auth.

**Acceptance Criteria:**
- Files land in correct Bronze subfolder by type
- Upload uses Managed Identity (no storage account key in code)
- Upload failures are logged and retried once before raising exception

---

## User Story 1.3 — Operational Logs Extractor

```
Work Item Type : User Story
Title          : Build operational log extractor landing raw logs to Bronze
Parent Epic    : Epic 1 — Secure On-Prem Data Extraction
Area Path      : ITSM-Chatbot\Data-Engineering
Priority       : 2 (High)
Story Points   : 5
Iteration      : Sprint 2
```

**Description:**
As a data engineer, I need operational log data extracted and landed in `raw/logs/*` in Bronze so that log context is available for downstream enrichment of the knowledge corpus.

**Acceptance Criteria:**
- Logs land in `raw/logs/{YYYY-MM-DD}/` partitioned by date
- Log format identified and validated (JSONL, CSV, or structured text)
- Volume anomaly guard: alert if daily volume is 5x rolling 7-day average
- Extractor runs as part of the Databricks scheduled Job

### Task 1.3.1

```
Title       : Identify log source format and build log_extractor.py
Assigned To : Data Engineer
Estimate    : 1 day
Priority    : 2 (High)
```

**Description:**
Confirm log source format (Windows Event Log / Syslog / App logs). Create `src/etl/extract/log_extractor.py`:
- Connect to log source
- Extract logs for the current run window (last 24h for daily runs)
- Write to `raw/logs/{YYYY-MM-DD}/logs_{batch_id}.jsonl` in Bronze

**Acceptance Criteria:**
- Log records include: `timestamp`, `event_type`, `source_system`, `message`, `affected_ci`
- Output is valid JSONL (one JSON object per line)
- Confirmed landing in correct Bronze path

---

### Task 1.3.2

```
Title       : Add log volume anomaly guard
Assigned To : Data Engineer
Estimate    : 0.5 days
Priority    : 3 (Medium)
```

**Description:**
After extraction, compare today's record count against 7-day rolling average stored in `etl-state/log_volume_history.json`. If today > 5x average, emit Azure Monitor custom metric alert `log_volume_anomaly` and continue pipeline (do not block).

**Acceptance Criteria:**
- Alert fires correctly when test data exceeds 5x threshold
- Pipeline continues after alert — does not fail the job
- Volume history file is updated each run

---

---

# EPIC 2 — Bronze Layer: Raw Data Landing

```
Work Item Type : Epic
Title          : Bronze Layer — Raw Data Landing in Azure Blob Storage
Area Path      : ITSM-Chatbot\Data-Engineering
Priority       : 1 (Critical)
Story Points   : 13
```

**Description:**
Organise and validate raw data as it lands in Azure Blob Storage Bronze zone (`raw/itsm/*`, `raw/docs/*`, `raw/logs/*`). Bronze is the immutable, replayable source of truth. No transformation happens here — only landing, partitioning, and metadata tagging.

**Acceptance Criteria:**
- All three source streams land in correct Bronze folder structure
- Each batch has a metadata sidecar file with extraction provenance
- Bronze data is partitioned by `object_type` and `date` for efficient reads
- Re-running extraction does not overwrite or duplicate already-landed records
- Bronze data is never modified after landing (append-only)

---

## User Story 2.1 — Bronze Storage Structure and Partitioning

```
Work Item Type : User Story
Title          : Define and provision Bronze blob storage structure with partitioning
Parent Epic    : Epic 2 — Bronze Layer
Area Path      : ITSM-Chatbot\Data-Engineering
Priority       : 1 (Critical)
Story Points   : 3
Iteration      : Sprint 1
```

**Description:**
As a data engineer, I need the Bronze Azure Blob container structured with consistent partitioning so that Databricks notebooks can efficiently read only the data they need for a given run date.

**Acceptance Criteria:**
- Container named `bronze` provisioned in Azure Blob Storage GCC
- Folder structure follows: `raw/{source}/{object_type}/{YYYY-MM-DD}/`
- Ivanti path example: `raw/itsm/incidents/2026-06-01/batch_001.json`
- Docs path example: `raw/docs/pdf/2026-06-01/procedure_guide.pdf`
- Images path example: `raw/docs/images/2026-06-01/screenshot_001.png`
- Logs path example: `raw/logs/2026-06-01/logs_001.jsonl`

### Task 2.1.1

```
Title       : Provision Bronze blob container with private endpoint and RBAC
Assigned To : DevOps / Data Engineer
Estimate    : 0.5 days
Priority    : 1 (Critical)
```

**Description:**
Provision Azure Blob Storage container `bronze` in GCC:
- Disable public blob access
- Enable private endpoint (VNet-scoped access only)
- Assign `Storage Blob Data Contributor` role to Databricks Managed Identity
- Assign `Storage Blob Data Reader` role to Silver pipeline Managed Identity

**Acceptance Criteria:**
- Public access blocked — direct URL access returns 403
- Databricks cluster can write a test file via Managed Identity
- No storage account key used anywhere in pipeline code

---

### Task 2.1.2

```
Title       : Write Bronze metadata sidecar generator
Assigned To : Data Engineer
Estimate    : 0.5 days
Priority    : 2 (High)
```

**Description:**
For every batch landed in Bronze, generate a `_metadata.json` sidecar file in the same folder:

```json
{
  "batch_id": "uuid",
  "source": "ivanti_incidents",
  "extracted_at": "2026-06-01T02:05:33Z",
  "record_count": 342,
  "pipeline_run_id": "adf_run_xyz",
  "full_load": false
}
```

**Acceptance Criteria:**
- Sidecar file created alongside every batch file
- `batch_id` is a UUID unique per batch
- `record_count` matches actual records in the batch file

---

---

# EPIC 3 — Silver Layer: Normalize to Medallion Schema

```
Work Item Type : Epic
Title          : Silver Layer — Normalize, Clean and Validate Bronze Data to Parquet
Area Path      : ITSM-Chatbot\Data-Engineering
Priority       : 1 (Critical)
Story Points   : 34
```

**Description:**
Transform raw Bronze data into clean, validated, schema-consistent Parquet files: `silver/itsm_tickets.parquet`, `silver/kb_docs.parquet`, `silver/kb_images/*`. This layer applies schema enforcement, HTML stripping, timestamp normalisation, enum validation, deduplication, and PII scrubbing. All Silver outputs are written as Parquet for efficient downstream reads.

**Acceptance Criteria:**
- All three Silver outputs exist and match their defined schemas
- Zero null values in mandatory fields (`ticket_id`, `content`, `created_at`)
- All `category`/`status` fields validated against approved enum lists
- All timestamps in UTC ISO-8601 format
- PII removed from `symptom`, `resolution`, and `content` fields
- Duplicate records removed (latest version kept by `lastModifiedDate`)
- QA report generated per run with pass/fail/quarantine counts

---

## User Story 3.1 — ITSM Tickets Silver Transformer

```
Work Item Type : User Story
Title          : Build Silver transformer for Ivanti ITSM tickets to itsm_tickets.parquet
Parent Epic    : Epic 3 — Silver Layer
Area Path      : ITSM-Chatbot\Data-Engineering
Priority       : 1 (Critical)
Story Points   : 13
Iteration      : Sprint 2
```

**Description:**
As a data engineer, I need a Databricks notebook that reads raw Ivanti JSON from Bronze, normalises and validates each record, and writes the result to `silver/itsm_tickets.parquet`, so that downstream Gold curation has a clean, consistent schema to work from.

**Acceptance Criteria:**
- Reads all batch JSON files from `raw/itsm/{object_type}/{run_date}/`
- Output Parquet schema: `ticket_id`, `type`, `subject`, `symptom_clean`, `resolution_clean`, `category`, `team`, `status`, `priority`, `created_at_utc`, `resolved_at_utc`, `ci_name`, `source_object_type`
- HTML stripped from `symptom` and `resolution` fields
- All `category` values validated — invalid values quarantined
- Timestamps normalised to UTC
- Deduplication: one row per `ticket_id` (latest by `lastModifiedDate`)

### Task 3.1.1

```
Title       : Create 01_silver_itsm.py Databricks notebook
Assigned To : Data Engineer
Estimate    : 2 days
Priority    : 1 (Critical)
```

**Description:**
Create `notebooks/01_silver_itsm.py`:
- Read Bronze JSON using PySpark or pandas (choose based on data volume)
- Flatten OData response envelope (`_value` array)
- Map OData field names to Silver schema field names
- Write output to `silver/itsm_tickets.parquet` (append mode, partitioned by `type`)

**Acceptance Criteria:**
- Notebook runs end-to-end in Databricks without errors on sample data
- Output Parquet readable by subsequent notebooks
- Partition column `type` exists in output (`incidents/problems/changes/kb_articles`)

---

### Task 3.1.2

```
Title       : Implement HTML stripper for symptom and resolution fields
Assigned To : Data Engineer
Estimate    : 0.5 days
Priority    : 1 (Critical)
```

**Description:**
Add HTML cleaning step to `01_silver_itsm.py`:
- Use `BeautifulSoup4` to strip HTML tags from `symptom` and `description` fields
- Preserve line breaks: `<br>` and `<p>` tags → `"\n"`
- Strip all other HTML tags
- Replace HTML entities (`&amp;` `&lt;` `&gt;` etc.) with plain text equivalents

**Acceptance Criteria:**
- Test input `"<p>Server <b>CPU</b> is high.<br/>Please restart.</p>"` produces `"Server CPU is high.\nPlease restart."`
- No HTML tags present in Silver output fields

---

### Task 3.1.3

```
Title       : Implement enum validation and quarantine for invalid category values
Assigned To : Data Engineer
Estimate    : 0.5 days
Priority    : 1 (Critical)
```

**Description:**
Add enum validation for `category` and `status` fields:
- Load allowed values from `config/enum_lookups.json` (align with enums in `src/api/ivanti/main.py`)
- Records with invalid `category` OR `status` values → write to `silver/quarantine/{run_date}/invalid_enum_{batch_id}.parquet`
- Valid records continue to `silver/itsm_tickets.parquet`
- Log quarantine count per run

**Acceptance Criteria:**
- Record with invalid category is NOT in `itsm_tickets.parquet`
- Same record IS in quarantine output with field `quarantine_reason`
- Valid records unaffected

---

### Task 3.1.4

```
Title       : Implement deduplication — one row per ticket_id, latest version
Assigned To : Data Engineer
Estimate    : 0.5 days
Priority    : 1 (Critical)
```

**Description:**
Add deduplication step before writing Silver output:
- Group by `ticket_id`
- Keep row with `max(lastModifiedDate)` per group
- Log count of duplicates removed per run

**Acceptance Criteria:**
- If Bronze has 3 versions of `INC-001` (different `lastModifiedDate`), Silver has exactly 1 row for `INC-001` (the latest)
- Duplicate count logged as pipeline metric

---

### Task 3.1.5

```
Title       : Implement PII scrubbing on symptom and resolution fields
Assigned To : Data Engineer
Estimate    : 2 days
Priority    : 1 (Critical)
```

**Description:**
Add PII scrubbing step using Microsoft Presidio (`presidio-analyzer` + `presidio-anonymizer`):
- Detect and redact: `EMAIL_ADDRESS`, `PHONE_NUMBER`, `PERSON` name entities
- Replace with placeholder tokens: `[EMAIL]`, `[PHONE]`, `[PERSON]`
- Apply to `symptom_clean` and `resolution_clean` fields
- PII scrubbing runs AFTER HTML stripping, BEFORE writing to Silver Parquet

**Acceptance Criteria:**
- `"Contact john.doe@company.com or call 555-1234"` becomes `"Contact [EMAIL] or call [PHONE]"`
- Test coverage confirms scrubbing does not remove non-PII text
- Processing time acceptable for expected batch size (benchmark on 10k records)

---

## User Story 3.2 — KB Docs Silver Transformer

```
Work Item Type : User Story
Title          : Build Silver transformer for Knowledge Docs to kb_docs.parquet
Parent Epic    : Epic 3 — Silver Layer
Area Path      : ITSM-Chatbot\Data-Engineering
Priority       : 1 (Critical)
Story Points   : 8
Iteration      : Sprint 2
```

**Description:**
As a data engineer, I need a Databricks notebook that reads raw KB documents (PDF, DOCX, HTML) from Bronze, extracts clean text and section structure, and writes the result to `silver/kb_docs.parquet`.

**Acceptance Criteria:**
- Reads PDF, DOCX, and HTML files from `raw/docs/{run_date}/`
- Output Parquet schema: `doc_id`, `title`, `content_type`, `sections` (JSON array), `full_text`, `source_file`, `last_modified`
- Section structure preserved where detectable (headings → `sections[]`)
- PII scrubbing applied to `full_text` and `sections` content
- Deduplication by content hash — same document ingested twice produces one row

### Task 3.2.1

```
Title       : Create 02_silver_kb_docs.py — text extraction from PDF/DOCX/HTML
Assigned To : Data Engineer
Estimate    : 2 days
Priority    : 1 (Critical)
```

**Description:**
Create `notebooks/02_silver_kb_docs.py`:
- PDF extraction: `pdfplumber` — extract text page by page
- DOCX extraction: `python-docx` — extract paragraphs with heading levels
- HTML extraction: `BeautifulSoup4` — extract text, detect `<h1>/<h2>` as sections
- Build `sections[]` JSON array: `[{heading, content}, ...]`
- Write to `silver/kb_docs.parquet`

**Acceptance Criteria:**
- All three file types extract non-empty text on test documents
- `sections` array populated for documents with detectable headings
- Corrupted/unreadable files quarantined to `silver/quarantine/` with error reason

---

### Task 3.2.2

```
Title       : Apply PII scrubbing and content-hash deduplication to KB docs
Assigned To : Data Engineer
Estimate    : 0.5 days
Priority    : 1 (Critical)
```

**Description:**
Reuse PII scrubbing module from Task 3.1.5 on `full_text` and `sections[].content` fields. Add SHA-256 content hash deduplication:
- Compute hash of `full_text` for each document
- Skip writing to Silver if hash already exists in `silver/kb_docs.parquet`
- Update hash registry after write

**Acceptance Criteria:**
- Same document uploaded twice produces one Silver row
- PII patterns removed from extracted text

---

## User Story 3.3 — KB Images Silver Cataloguer

```
Work Item Type : User Story
Title          : Build Silver image cataloguer producing kb_images manifest
Parent Epic    : Epic 3 — Silver Layer
Area Path      : ITSM-Chatbot\Data-Engineering
Priority       : 2 (High)
Story Points   : 5
Iteration      : Sprint 3
```

**Description:**
As a data engineer, I need a Databricks notebook that inventories all raw images from Bronze, validates them, and produces `silver/kb_images/image_manifest.parquet` with metadata for each image, so that the Gold layer can embed and serve them.

**Acceptance Criteria:**
- Reads all images from `raw/docs/images/{run_date}/`
- Validates: image is not corrupted, file size > 1KB, dimensions > 50x50px
- Output manifest schema: `image_id` (UUID), `source_path`, `silver_path`, `parent_doc_id`, `alt_text` (filename fallback), `file_size_kb`
- Validated images copied to `silver/kb_images/{image_id}.{ext}`
- Corrupted images quarantined with reason

### Task 3.3.1

```
Title       : Create 03_silver_kb_images.py — image validation and cataloguing
Assigned To : Data Engineer
Estimate    : 1 day
Priority    : 2 (High)
```

**Description:**
Create `notebooks/03_silver_kb_images.py`:
- Read image file list from `raw/docs/images/{run_date}/`
- Validate each image using `Pillow`: open, check dimensions, check file size
- Generate UUID `image_id` for each valid image
- Link to parent doc via filename pattern matching (image filename contains `doc_id` prefix)
- Copy valid images to `silver/kb_images/{image_id}.{ext}`
- Write `image_manifest.parquet`

**Acceptance Criteria:**
- Corrupted image (truncated file) caught and quarantined
- Image smaller than 50x50px quarantined with reason `"below_minimum_dimensions"`
- `manifest.parquet` row count equals valid image count

---

---

# EPIC 4 — Gold Layer: Curated RAG Corpus

```
Work Item Type : Epic
Title          : Gold Layer — Curate Final RAG Corpus (corpus_text, corpus_images, metadata)
Area Path      : ITSM-Chatbot\Data-Engineering
Priority       : 1 (Critical)
Story Points   : 21
```

**Description:**
Transform Silver outputs into the final three Gold artifacts that feed the embedding and indexing pipeline: `gold/corpus_text.parquet` (chunked text units), `gold/corpus_images/*` (validated images ready for embedding), and `gold/metadata.parquet` (unified provenance and SAS URL registry). This is the final ETL stage. Output quality directly determines chatbot answer quality.

**Acceptance Criteria:**
- `gold/corpus_text.parquet` contains one row per text chunk with all metadata fields
- `gold/corpus_images/` contains all validated images from Silver
- `gold/metadata.parquet` is a complete registry of all corpus artifacts
- All three Gold outputs regenerated cleanly on every pipeline run
- Chunking is deterministic — same input always produces same chunks

---

## User Story 4.1 — Text Chunker producing corpus_text.parquet

```
Work Item Type : User Story
Title          : Build Gold text chunker producing corpus_text.parquet from Silver outputs
Parent Epic    : Epic 4 — Gold Layer
Area Path      : ITSM-Chatbot\Data-Engineering
Priority       : 1 (Critical)
Story Points   : 8
Iteration      : Sprint 3
```

**Description:**
As a data engineer, I need a Databricks notebook that reads Silver ITSM tickets and KB docs, applies a chunking strategy appropriate for each source type, and writes all chunks to `gold/corpus_text.parquet` so that the embedding pipeline has retrieval-optimized text units.

**Acceptance Criteria:**
- ITSM tickets chunked as single units: `subject + symptom + resolution` concatenated
- KB docs chunked by section: max 512 tokens per chunk, 10% overlap between chunks
- Each chunk has: `chunk_id` (UUID), `source_type`, `source_id`, `chunk_index`, `token_count`, `text_content`, `category`, `team`, `created_date`
- Zero chunks with empty `text_content`
- Chunking is deterministic (same input = same `chunk_id`)

### Task 4.1.1

```
Title       : Create 05_gold_text.py — chunking notebook for tickets and KB docs
Assigned To : Data Engineer
Estimate    : 2 days
Priority    : 1 (Critical)
```

**Description:**
Create `notebooks/05_gold_text.py`:
- Read `silver/itsm_tickets.parquet` and `silver/kb_docs.parquet`
- ITSM ticket chunking: one chunk per ticket — concatenate `"Subject: {subject}\nSymptom: {symptom_clean}\nResolution: {resolution_clean}"`
- KB doc chunking: section-aware sliding window, max 512 tokens, 10% overlap using `tiktoken` (`cl100k_base` encoding to match GPT-4o tokenizer)
- Assign deterministic `chunk_id`: `UUID5(namespace=source_id, name=str(chunk_index))`
- Write to `gold/corpus_text.parquet`

**Acceptance Criteria:**
- Ticket chunks: one row per `ticket_id` in `itsm_tickets.parquet`
- KB chunks: section chunks ≤ 512 tokens each (validated by token count column)
- Overlap verified: last 10% of chunk N == first 10% of chunk N+1
- No empty `text_content` rows

---

### Task 4.1.2

```
Title       : Add token count validation and oversized chunk handling
Assigned To : Data Engineer
Estimate    : 0.5 days
Priority    : 2 (High)
```

**Description:**
After chunking, validate all chunks:
- Log warning for any chunk > 512 tokens (ITSM tickets with very long content)
- For oversized ticket chunks, apply hard truncation at 1024 tokens with suffix `"[truncated]"`
- Log count of truncated records per run

**Acceptance Criteria:**
- No chunk in `corpus_text.parquet` exceeds 1024 tokens
- Truncated chunks have `"[truncated]"` appended to `text_content`
- Truncation count emitted as pipeline metric

---

## User Story 4.2 — Image Gold Promotion

```
Work Item Type : User Story
Title          : Promote validated Silver images to Gold corpus_images with SAS URL generation
Parent Epic    : Epic 4 — Gold Layer
Area Path      : ITSM-Chatbot\Data-Engineering
Priority       : 2 (High)
Story Points   : 5
Iteration      : Sprint 3
```

**Description:**
As a data engineer, I need validated Silver images copied to `gold/corpus_images/` and SAS URLs generated for each, so that the chatbot can serve image content directly from Blob Storage without embedding image bytes in the search index.

**Acceptance Criteria:**
- All valid Silver images copied to `gold/corpus_images/{image_id}.{ext}`
- SAS URLs generated with read-only access and 365-day expiry
- SAS URLs stored in `gold/metadata.parquet` against `image_id`
- SAS URL rotation job scheduled to refresh URLs 30 days before expiry

### Task 4.2.1

```
Title       : Create 06_gold_images.py — copy Silver images to Gold and generate SAS URLs
Assigned To : Data Engineer
Estimate    : 1 day
Priority    : 2 (High)
```

**Description:**
Create `notebooks/06_gold_images.py`:
- Read `silver/kb_images/image_manifest.parquet`
- Copy each image from `silver/kb_images/` to `gold/corpus_images/{image_id}.{ext}` using `azure-storage-blob BlobClient` (Managed Identity)
- Generate SAS URL per image: read-only, 365-day expiry, using `generate_blob_sas()` with stored access policy
- Return DataFrame with columns: `image_id`, `gold_path`, `sas_url`, `expiry_date`

**Acceptance Criteria:**
- Images land in `gold/corpus_images/` with correct names
- SAS URL for each image is accessible (HTTP 200) from Azure environment
- Expiry date is exactly 365 days from run date
- No storage account key used (delegation key via Managed Identity)

---

### Task 4.2.2

```
Title       : Build SAS URL rotation Azure Function (30-day pre-expiry refresh)
Assigned To : Data Engineer / DevOps
Estimate    : 1 day
Priority    : 2 (High)
```

**Description:**
Create an Azure Function (timer trigger, runs daily) that:
- Reads `gold/metadata.parquet`
- Finds all images with `expiry_date` within 30 days
- Regenerates SAS URLs for those images with new 365-day expiry
- Writes updated `metadata.parquet` back to Gold

**Acceptance Criteria:**
- Function triggers daily without manual intervention
- Images with expiry ≤ 30 days get new SAS URLs
- Updated `expiry_date` written back to `metadata.parquet`
- Function uses Managed Identity — no storage key

---

## User Story 4.3 — Gold Metadata Registry

```
Work Item Type : User Story
Title          : Build unified Gold metadata.parquet registry for all corpus artifacts
Parent Epic    : Epic 4 — Gold Layer
Area Path      : ITSM-Chatbot\Data-Engineering
Priority       : 1 (Critical)
Story Points   : 5
Iteration      : Sprint 3
```

**Description:**
As a data engineer, I need `gold/metadata.parquet` to serve as a single registry that maps every corpus artifact (text chunk or image) to its provenance, so that any downstream consumer can resolve an `artifact_id` to its full context.

**Acceptance Criteria:**
- Schema: `artifact_id`, `artifact_type` (`text_chunk`/`image`), `source_type`, `source_id`, `category`, `team`, `created_date`, `sas_url` (images only, null for text), `pipeline_run_id`, `pipeline_run_date`
- One row per artifact — no duplicates
- Every image in `corpus_images` has a row; every chunk in `corpus_text` has a row
- Written last in the Gold pipeline stage after both notebooks 05 and 06 complete

### Task 4.3.1

```
Title       : Create 07_gold_metadata.py — merge text chunk and image metadata
Assigned To : Data Engineer
Estimate    : 1 day
Priority    : 1 (Critical)
```

**Description:**
Create `notebooks/07_gold_metadata.py` (runs after 05 and 06):
- Read `gold/corpus_text.parquet` — emit one metadata row per `chunk_id`
- Read output DataFrame from `06_gold_images.py` — emit one metadata row per `image_id`
- Union both DataFrames into unified metadata schema
- Add `pipeline_run_id` and `pipeline_run_date` columns
- Write to `gold/metadata.parquet` (overwrite mode — full refresh each run)

**Acceptance Criteria:**
- Row count = chunk count (from `corpus_text`) + image count (from `corpus_images`)
- No duplicate `artifact_id` values
- All image rows have non-null `sas_url`
- All text chunk rows have null `sas_url`

---

---

# EPIC 5 — Pipeline Orchestration & Automation

```
Work Item Type : Epic
Title          : Databricks Workflow — Automate End-to-End ETL Pipeline on Schedule
Area Path      : ITSM-Chatbot\Data-Engineering
Priority       : 1 (Critical)
Story Points   : 13
```

**Description:**
Wire all ETL notebooks into a single Databricks Workflow (Job) that runs automatically on a daily cron schedule. This is the automation layer — the mechanism that makes Option B real. No human runs the pipeline. The platform runs it, monitors it, and retries on failure.

**Acceptance Criteria:**
- Single Databricks Job `ivanti-itsm-etl-daily` runs all pipeline stages in order
- Job runs automatically at 02:00 AM UTC every day
- Job fails fast and sends alert if any stage fails after 3 retries
- Incremental mode is the default; full-load mode available via job parameter
- Pipeline run history retained for 30 days in Databricks Jobs UI

---

## Databricks Workflow Task Dependency Graph

```
extract_ivanti ──┐
extract_kb_docs ─┼──► bronze_validate ──► silver_itsm ────┐
extract_logs ────┘                         silver_kb_docs ──┼──► qa_gate ──► gold_text ────┐
                                           silver_images ───┘              gold_images ────┼──► gold_metadata
                                                                                            │
                                                                           (parallel) ──────┘
```

---

## User Story 5.1 — Databricks Workflow Definition

```
Work Item Type : User Story
Title          : Define and deploy Databricks Workflow for automated daily ETL execution
Parent Epic    : Epic 5 — Pipeline Orchestration
Area Path      : ITSM-Chatbot\Data-Engineering
Priority       : 1 (Critical)
Story Points   : 8
Iteration      : Sprint 4
```

**Description:**
As a data engineer, I need a Databricks Workflow that chains all ETL notebooks in the correct dependency order and runs automatically every night, so that the Gold corpus is updated without any manual steps.

**Acceptance Criteria:**
- Workflow defined as code in `databricks_workflow.yml` (version-controlled)
- Execution order enforced by `depends_on` task dependencies
- Failed task blocks all downstream tasks — partial runs do not produce incomplete Gold
- Job parameters: `run_date` (default: today), `mode` (`incremental`/`full`), `object_types[]`
- Retry policy: 3 retries per task, 10-minute delay between retries
- On final failure: send email alert to data-engineering team

### Task 5.1.1

```
Title       : Define Databricks Workflow as YAML config (databricks_workflow.yml)
Assigned To : Data Engineer / DevOps
Estimate    : 1.5 days
Priority    : 1 (Critical)
```

**Description:**
Create `databricks_workflow.yml` using Databricks Asset Bundle format defining:
- Job name: `ivanti-itsm-etl-daily`
- Cluster: existing shared cluster or job cluster (choose based on cost model)
- Tasks: one task per notebook with `depends_on` dependencies (see graph above)
- Parameters: `run_date`, `mode`, `object_types`
- Retry: `max_retries=3`, `retry_on_timeout=true`
- Email notifications: `on_failure` → `data-eng-alerts@company.com`

**Acceptance Criteria:**
- YAML is valid Databricks Asset Bundle format
- Workflow deployed to Databricks workspace via `databricks bundle deploy`
- All task dependencies correctly enforce execution order
- Deployable from CI/CD pipeline without manual UI steps

---

### Task 5.1.2

```
Title       : Configure daily 02:00 AM UTC cron trigger on Databricks Workflow
Assigned To : Data Engineer / DevOps
Estimate    : 0.5 days
Priority    : 1 (Critical)
```

**Description:**
Add schedule trigger to `databricks_workflow.yml`:
- `cron: "0 2 * * *"` (02:00 AM UTC daily)
- `timezone: UTC`
- `pause_status: UNPAUSED` (active immediately after deploy)

**Acceptance Criteria:**
- Job runs automatically at 02:00 AM UTC on the next scheduled day after deploy
- Job does not run more than once per day
- Schedule visible and editable in Databricks Jobs UI

---

### Task 5.1.3

```
Title       : Implement pipeline watermark/cursor store for incremental runs
Assigned To : Data Engineer
Estimate    : 1 day
Priority    : 1 (Critical)
```

**Description:**
Create `etl-state/` folder in Azure Blob as the pipeline state store:

```
etl-state/
  cursors/
    incidents.json      → {"last_run": "2026-06-01T02:00:00Z", "last_id": "INC-9999"}
    problems.json
    changes.json
    kb_articles.json
    kb_files.json
  kb_hash_manifest.json
  log_volume_history.json
```

Create `src/etl/utils/cursor_store.py`:
- `read_cursor(object_type) → dict`
- `write_cursor(object_type, last_run, last_id)`
- Uses Blob optimistic concurrency (ETag check) to prevent race conditions

**Acceptance Criteria:**
- `read_cursor` returns correct `last_run` on second pipeline run
- `write_cursor` updates file atomically (no partial writes)
- Full-load mode ignores cursor (`read_cursor` returns `None`, extract all records)
- Cursor is only updated AFTER successful downstream stage completes

---

### Task 5.1.4

```
Title       : Configure pipeline failure alerting via Azure Monitor and Teams
Assigned To : DevOps
Estimate    : 0.5 days
Priority    : 1 (Critical)
```

**Description:**
Configure failure notification for Databricks Job:
- On job failure: send email to data-engineering alert group
- On job failure: emit custom Azure Monitor metric `etl_job_failed = 1`
- Create Azure Monitor alert rule: if `etl_job_failed > 0`, post notification to ITSM-Ops Teams channel

**Acceptance Criteria:**
- Test: manually fail a notebook task → confirm email received within 5 minutes
- Test: manually fail task → confirm Teams channel message posted
- Successful runs do not trigger alerts

---

## User Story 5.2 — Full-Load and On-Demand Run Support

```
Work Item Type : User Story
Title          : Support full-load and on-demand pipeline runs via Databricks Job parameters
Parent Epic    : Epic 5 — Pipeline Orchestration
Area Path      : ITSM-Chatbot\Data-Engineering
Priority       : 2 (High)
Story Points   : 3
Iteration      : Sprint 4
```

**Description:**
As a data engineer, I need to trigger a full re-load of all Ivanti data on demand (e.g., after a schema change) without modifying the scheduled job config, so that I can re-seed the corpus without editing production configuration.

**Acceptance Criteria:**
- Databricks Job accepts parameter `mode=full` which bypasses delta cursor
- Full-load can be triggered manually from Databricks UI or via REST API call
- Full-load clears and rewrites Gold outputs (does not append to existing)
- On-demand run for a specific object type only: `object_types=["incidents"]`

### Task 5.2.1

```
Title       : Add mode and object_types parameters to all pipeline notebooks
Assigned To : Data Engineer
Estimate    : 1 day
Priority    : 2 (High)
```

**Description:**
Update all ETL notebooks to read Databricks widget parameters:
- `dbutils.widgets.get("mode")` → `"incremental"` (default) or `"full"`
- `dbutils.widgets.get("object_types")` → JSON array, default `["incidents","problems","changes","kb_articles"]`
- In full mode: ignore cursor, extract all records, overwrite Silver/Gold outputs
- In incremental mode: use cursor, append to Silver, upsert Gold

**Acceptance Criteria:**
- Running job with `mode=full` produces complete re-extraction regardless of cursor state
- Running job with `object_types=["incidents"]` only extracts and transforms incidents
- Default run (no params) behaves as incremental for all object types

---

---

## Story Points Summary

| Epic | Title | Priority | Story Points |
|------|-------|----------|-------------|
| Epic 1 | Secure On-Prem Data Extraction | 1 — Critical | 34 |
| Epic 2 | Bronze Layer: Raw Data Landing | 1 — Critical | 13 |
| Epic 3 | Silver Layer: Normalize to Medallion Schema | 1 — Critical | 34 |
| Epic 4 | Gold Layer: Curated RAG Corpus | 1 — Critical | 21 |
| Epic 5 | Pipeline Orchestration & Automation | 1 — Critical | 13 |
| | **Total** | | **115** |

---

## Sprint Allocation

| Sprint | Focus | Epics | Key Deliverables |
|--------|-------|-------|-----------------|
| Sprint 1 | Foundation | E1 + E2 | Ivanti connector live, KB extractor live, Bronze landing automated |
| Sprint 2 | Silver Transform | E1 (logs) + E3 (tickets + KB docs) | `itsm_tickets.parquet` and `kb_docs.parquet` clean and PII-free |
| Sprint 3 | Gold Corpus | E3 (images) + E4 | All three Gold artifacts produced: `corpus_text`, `corpus_images`, `metadata` |
| Sprint 4 | Automation | E5 | Databricks Workflow running on schedule, cursor store live, alerts configured |

---

## Notebook Execution Order Reference

| Order | Notebook | Input | Output |
|-------|----------|-------|--------|
| 1 | `extract_ivanti.py` | Ivanti HEAT OData API | `raw/itsm/*/` |
| 2 | `extract_kb_docs.py` | On-prem file share | `raw/docs/*/` |
| 3 | `extract_logs.py` | Log source | `raw/logs/*/` |
| 4 | `bronze_validate.py` | All `raw/` paths | Metadata sidecars |
| 5 | `01_silver_itsm.py` | `raw/itsm/*/` | `silver/itsm_tickets.parquet` |
| 6 | `02_silver_kb_docs.py` | `raw/docs/*/` | `silver/kb_docs.parquet` |
| 7 | `03_silver_kb_images.py` | `raw/docs/images/*/` | `silver/kb_images/*` + `image_manifest.parquet` |
| 8 | `04_qa_gate.py` | All Silver outputs | QA report + quarantine files |
| 9 | `05_gold_text.py` | Silver tickets + KB docs | `gold/corpus_text.parquet` |
| 10 | `06_gold_images.py` | Silver image manifest | `gold/corpus_images/*` + SAS URLs |
| 11 | `07_gold_metadata.py` | Gold text + Gold images | `gold/metadata.parquet` |

---

*Document generated: 2026-06-01*
*Area Path: ITSM-Chatbot\Data-Engineering*
*Next phase: Embedding & Index Build (Epic 6) — to be planned after ETL pipeline is validated in staging.*
