# =============================================================================
# nice-api — NICE inContact FastAPI service
# Build context: project root (.) so we can reach certs/ and src/api/nice_incontact/
# =============================================================================
FROM python:3.11-slim

WORKDIR /app

# -----------------------------------------------------------------------------
# Step 1: Bake corporate CA certificate into the system trust store
# -----------------------------------------------------------------------------
COPY certs/ /tmp/certs/

RUN apt-get update -qq && apt-get install -y --no-install-recommends ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    if ls /tmp/certs/*.crt 2>/dev/null; then \
        cp /tmp/certs/*.crt /usr/local/share/ca-certificates/; \
    fi && \
    update-ca-certificates && \
    rm -rf /tmp/certs

ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV PIP_CERT=/etc/ssl/certs/ca-certificates.crt

# -----------------------------------------------------------------------------
# Step 2: Install Python dependencies
# -----------------------------------------------------------------------------
COPY src/api/nice_incontact/requirements.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# -----------------------------------------------------------------------------
# Step 3: Copy application code
# -----------------------------------------------------------------------------
COPY src/api/nice_incontact/ .

# -----------------------------------------------------------------------------
# Step 4: Runtime configuration
# -----------------------------------------------------------------------------
EXPOSE 8001

ENV PYTHONUNBUFFERED=1
ENV PORT=8001

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c \
        "import urllib.request; \
         urllib.request.urlopen('http://localhost:8001/')" \
        || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
