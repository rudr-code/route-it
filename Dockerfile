# ===================================================================
# Route.it - Quantum-Inspired Intelligent Delivery System
# Multi-Stage Production Dockerfile (Frontend SPA + FastAPI Backend)
# Optimized for Render Free Tier (512 MB RAM)
# ===================================================================

# -------------------------------------------------------------------
# Stage 1: Build React Vite Dashboard
# -------------------------------------------------------------------
FROM node:20-alpine AS frontend-builder
WORKDIR /app/dashboard

COPY dashboard/package*.json ./
RUN npm install

COPY dashboard/ ./
RUN npm run build

# -------------------------------------------------------------------
# Stage 2: Python Backend & Unified Fullstack Service
# -------------------------------------------------------------------
FROM python:3.11-slim AS production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8001 \
    DATA_DIR=/app/data

WORKDIR /app

# Minimal system runtime dependencies (curl for healthchecks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python backend dependencies using prebuilt wheels
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -e .

# Copy application source code
COPY api/ ./api/
COPY solver/ ./solver/
COPY routing/ ./routing/
COPY dynamic/ ./dynamic/
COPY benchmarks/ ./benchmarks/
COPY main.py ./

# Copy pre-compiled frontend assets from Stage 1 into dashboard/dist
COPY --from=frontend-builder /app/dashboard/dist ./dashboard/dist

# Ensure writable data directory exists
RUN mkdir -p /app/data

EXPOSE 8001

# Shell-form CMD to allow dynamic expansion of $PORT assigned by Render (or fallback 8001)
CMD ["sh", "-c", "python -m uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8001}"]
