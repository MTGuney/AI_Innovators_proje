# syntax=docker/dockerfile:1

FROM python:3.12-slim AS base

# libgomp1 is required by onnxruntime, which chromadb pulls in.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first so code edits do not invalidate the install layer.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts
COPY main.py ./

# Documents and the embedded vector store live on a mounted volume.
RUN mkdir -p /app/data/raw /app/data/uploads /app/data/chroma

# The Foundry CLI is not present in the image, so neither auto-load nor
# port discovery can work here: point FOUNDRY_LOCAL_URL at the host instead.
ENV DATA_DIR=/app/data \
    UPLOAD_DIR=/app/data/uploads \
    CHROMA_PERSIST_DIR=/app/data/chroma \
    FOUNDRY_AUTO_LOAD=false \
    FOUNDRY_AUTO_DISCOVER=false

# Run as a non-root user; it must own the data directory it writes to.
RUN useradd --create-home --uid 1001 finrag && chown -R finrag:finrag /app
USER finrag

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
