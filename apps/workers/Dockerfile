# CEQ Worker - ComfyUI GPU Worker Image
#
# Multi-stage build for production ComfyUI workers.
# Designed for deployment on Vast.ai and Furnace (Enclii).
#
# Build:
#   docker build -t ceq-worker:latest .
#
# Run:
#   docker run --gpus all -p 8188:8188 ceq-worker:latest

# =============================================================================
# Stage 1: Base image with CUDA and Python
# =============================================================================
FROM nvidia/cuda:12.4.0-runtime-ubuntu22.04 AS base

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-venv \
    python3-pip \
    git \
    git-lfs \
    wget \
    curl \
    ffmpeg \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Set Python 3.11 as default
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

# Create app user
RUN useradd -m -s /bin/bash ceq
WORKDIR /home/ceq

# =============================================================================
# Stage 2: ComfyUI installation
# =============================================================================
FROM base AS comfyui

# Clone ComfyUI
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /opt/comfyui

WORKDIR /opt/comfyui

# Install ComfyUI dependencies
RUN pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124 && \
    pip install --no-cache-dir -r requirements.txt

# Install commonly used custom nodes
RUN mkdir -p custom_nodes && \
    cd custom_nodes && \
    git clone https://github.com/ltdrdata/ComfyUI-Manager.git && \
    git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git && \
    git clone https://github.com/ssitu/ComfyUI_UltimateSDUpscale.git && \
    git clone https://github.com/cubiq/ComfyUI_IPAdapter_plus.git && \
    git clone https://github.com/Fannovel16/comfyui_controlnet_aux.git && \
    cd ..

# Install custom node dependencies
RUN cd custom_nodes/ComfyUI-Manager && pip install --no-cache-dir -r requirements.txt || true && \
    cd ../ComfyUI-VideoHelperSuite && pip install --no-cache-dir -r requirements.txt || true && \
    cd ../ComfyUI_UltimateSDUpscale && pip install --no-cache-dir -r requirements.txt || true && \
    cd ../ComfyUI_IPAdapter_plus && pip install --no-cache-dir -r requirements.txt || true && \
    cd ../comfyui_controlnet_aux && pip install --no-cache-dir -r requirements.txt || true

# =============================================================================
# Stage 3: CEQ Worker installation
# =============================================================================
FROM comfyui AS worker

# Create directories
RUN mkdir -p /opt/models /opt/outputs /opt/cache

# Copy CEQ worker code
COPY --chown=ceq:ceq . /app/ceq-worker

WORKDIR /app/ceq-worker

# Install CEQ worker
RUN pip install --no-cache-dir -e .

# Create model path configuration for ComfyUI
RUN cat > /opt/comfyui/extra_model_paths.yaml <<EOF
ceq_models:
    base_path: /opt/models
    checkpoints: checkpoints
    clip: clip
    clip_vision: clip_vision
    configs: configs
    controlnet: controlnet
    diffusers: diffusers
    embeddings: embeddings
    gligen: gligen
    hypernetworks: hypernetworks
    loras: loras
    style_models: style_models
    unet: unet
    upscale_models: upscale_models
    vae: vae
    vae_approx: vae_approx
EOF

# =============================================================================
# Stage 4: Production image
# =============================================================================
FROM worker AS production

# Environment
ENV COMFYUI_PATH=/opt/comfyui
ENV MODELS_PATH=/opt/models
ENV OUTPUTS_PATH=/opt/outputs
ENV CACHE_PATH=/opt/cache
ENV GPU_DEVICE=cuda:0

# Expose ComfyUI port
EXPOSE 8188

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -sf http://localhost:8188/system_stats || exit 1

# Volume mounts for models and outputs
VOLUME ["/opt/models", "/opt/outputs"]

# Default command: Run queue consumer
CMD ["python", "-m", "ceq_worker.queue"]

# =============================================================================
# Alternative: Run orchestrator
# =============================================================================
# docker run --gpus all ceq-worker:latest python -m ceq_worker.orchestrator

# =============================================================================
# Alternative: Run with ComfyUI only (for debugging)
# =============================================================================
# docker run --gpus all -p 8188:8188 ceq-worker:latest \
#   python /opt/comfyui/main.py --listen 0.0.0.0 --port 8188
