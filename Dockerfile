FROM python:3.12-slim

# Security: run as non-root
RUN groupadd -r velora && useradd -r -g velora velora

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (lean — no DB/Redis for MVP)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
        fastapi==0.115.5 \
        "uvicorn[standard]==0.32.1" \
        pydantic==2.10.1 \
        pydantic-settings==2.6.1 \
        httpx==0.28.0 \
        "croo-sdk>=0.1.0"

# Copy source code (WORKDIR is /app, so files land at /app/api/, /app/core/, etc.)
COPY --chown=velora:velora . .

# Create log directory
RUN mkdir -p /app/logs && chown velora:velora /app/logs

# Drop privileges
USER velora

# Health check using the /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8080}/health || exit 1

EXPOSE 8080

# Entry: app.py at /app/app.py imports from api.server — clean, no module path issues
CMD ["python", "-m", "uvicorn", "app:app", \
     "--host", "0.0.0.0", \
     "--port", "8080", \
     "--workers", "1", \
     "--log-level", "info"]
