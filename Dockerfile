# ═══════════════════════════════════════════════════════
# Pulse-Chennai GPU-Optimized Dockerfile
# ═══════════════════════════════════════════════════════
# Multi-stage build:
#   Stage 1 (builder): Install Python deps with CUDA
#   Stage 2 (runtime): Slim image with only runtime deps
#
# Target hardware: NVIDIA T4 / A100
# CUDA 12.1 + cuDNN 8 + PyTorch 2.2 + PyG
# ═══════════════════════════════════════════════════════

# ── Stage 1: Builder ──
FROM nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-dev \
    python3.11-venv \
    python3-pip \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Use python3.11 as default
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1

# Create venv
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install PyTorch with CUDA 12.1
RUN pip install --no-cache-dir \
    torch==2.2.0 \
    --index-url https://download.pytorch.org/whl/cu121

# Install PyG with CUDA extensions
RUN pip install --no-cache-dir \
    torch-geometric==2.5.0 \
    torch-scatter \
    torch-sparse \
    -f https://data.pyg.org/whl/torch-2.2.0+cu121.html

# Install project dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt


# ── Stage 2: Runtime ──
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Minimal runtime deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-venv \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1

# Copy venv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
WORKDIR /app
COPY . /app/

# Create models directory
RUN mkdir -p /app/models

# Expose port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')" || exit 1

# Run with Uvicorn
# Workers = 1 for GPU (CUDA contexts are per-process)
CMD ["uvicorn", "api.dashboard_server:app", \
     "--host", "0.0.0.0", \
     "--port", "8001", \
     "--workers", "1", \
     "--log-level", "info"]
