FROM python:3.12-slim

# Security: run as non-root
RUN groupadd -r velora && useradd -r -g velora velora

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy source
COPY --chown=velora:velora . .

# Create required directories
RUN mkdir -p /app/logs && chown velora:velora /app/logs

# Drop privileges
USER velora

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8080}/health || exit 1

EXPOSE 8080

CMD ["python", "-m", "uvicorn", "velora.api.server:app", \
     "--host", "0.0.0.0", \
     "--port", "8080", \
     "--workers", "1", \
     "--log-level", "warning", \
     "--no-access-log"]
