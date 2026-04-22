# =============================================================================
# teams-bot — ITSM AI Orchestrator
# Build context: project root (.)
# =============================================================================
FROM python:3.11-slim

WORKDIR /app

# -----------------------------------------------------------------------------
# Step 1: Bake corporate CA certificate into the system trust store.
# The certs/ directory at the project root must contain the .crt file.
# If it is empty the build still succeeds — Python will use the default bundle.
# This step must come BEFORE pip install so pip itself can reach PyPI through
# the corporate TLS-inspection proxy.
# -----------------------------------------------------------------------------
COPY certs/ /tmp/certs/

RUN apt-get update -qq && apt-get install -y --no-install-recommends ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    if ls /tmp/certs/*.crt 2>/dev/null; then \
        cp /tmp/certs/*.crt /usr/local/share/ca-certificates/; \
    fi && \
    update-ca-certificates && \
    rm -rf /tmp/certs

# Point every Python SSL library at the updated system bundle
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV PIP_CERT=/etc/ssl/certs/ca-certificates.crt

# -----------------------------------------------------------------------------
# Step 2: Install Python dependencies
# -----------------------------------------------------------------------------
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# -----------------------------------------------------------------------------
# Step 3: Copy application code
# -----------------------------------------------------------------------------
COPY src/ ./src/
COPY knowledge-bases/ ./knowledge-bases/

# -----------------------------------------------------------------------------
# Step 4: Runtime configuration
# -----------------------------------------------------------------------------
EXPOSE 3978

ENV PYTHONUNBUFFERED=1
ENV PORT=3978
ENV PYTHONPATH=/app/src

# Health check — no curl dependency needed
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c \
        "import urllib.request, os; \
         urllib.request.urlopen('http://localhost:' + os.environ.get('PORT','3978') + '/')" \
        || exit 1

CMD ["python", "src/teams_server.py"]
